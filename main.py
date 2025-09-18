#!/usr/bin/env python3
"""
Clean Google Calendar MCP Server
Built specifically for Railway deployment with ElevenLabs integration
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import io
import base64

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
import requests

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Google Calendar MCP Server", version="1.0.0")

# CORS middleware - Comprehensive for ElevenLabs MCP integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for maximum compatibility
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=[
        "*",
        "Content-Type",
        "Authorization", 
        "X-Requested-With",
        "Accept",
        "Origin",
        "User-Agent",
        "DNT",
        "Cache-Control",
        "X-Mx-ReqToken",
        "Keep-Alive",
        "X-CSRFToken"
    ],
    expose_headers=["*"]
)

# MCP Request/Response Models
class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int
    method: str
    params: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class MCPError(BaseModel):
    code: int
    message: str

# Tool definitions - compatible with both MCP and ElevenLabs
MCP_TOOLS = [
    {
        "name": "check_availability",
        "description": "Check available appointment slots for a specific date and time range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date to check (YYYY-MM-DD)"},
                "start_time": {"type": "string", "description": "Start time (HH:MM)"},
                "end_time": {"type": "string", "description": "End time (HH:MM)"},
                "duration": {"type": "integer", "description": "Appointment duration in minutes", "default": 60}
            },
            "required": ["date", "start_time", "end_time"]
        },
    },
    {
        "name": "book_appointment",
        "description": "Book a new dental appointment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                "time": {"type": "string", "description": "Appointment time (HH:MM)"},
                "duration": {"type": "integer", "description": "Duration in minutes", "default": 60},
                "patient_name": {"type": "string", "description": "Patient's name"},
                "patient_email": {"type": "string", "description": "Patient's email"},
                "phone": {"type": "string", "description": "Patient's phone number"},
                "service": {"type": "string", "description": "Type of service (cleaning, checkup, etc.)"}
            },
            "required": ["date", "time", "patient_name", "patient_email", "service"]
        }
    },
    {
        "name": "cancel_appointment",
        "description": "Cancel an existing appointment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string", "description": "Google Calendar event ID"},
                "reason": {"type": "string", "description": "Cancellation reason"}
            },
            "required": ["appointment_id"]
        }
    },
    {
        "name": "reschedule_appointment",
        "description": "Reschedule an existing appointment",
        "inputSchema": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string", "description": "Google Calendar event ID"},
                "new_date": {"type": "string", "description": "New date (YYYY-MM-DD)"},
                "new_time": {"type": "string", "description": "New time (HH:MM)"},
                "duration": {"type": "integer", "description": "Duration in minutes", "default": 60}
            },
            "required": ["appointment_id", "new_date", "new_time"]
        }
    },
    {
        "name": "get_appointments",
        "description": "Get appointments for a specific date range",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"}
            },
            "required": ["start_date", "end_date"]
        }
    },
    {
        "name": "find_next_available",
        "description": "Find the next available appointment slot",
        "inputSchema": {
            "type": "object",
            "properties": {
                "duration": {"type": "integer", "description": "Appointment duration in minutes", "default": 60},
                "days_ahead": {"type": "integer", "description": "How many days to search ahead", "default": 30}
            }
        }
    },
]

def get_calendar_service():
    """Create Google Calendar service with OAuth credentials"""
    try:
        # Get credentials from environment
        access_token = os.environ.get('GOOGLE_ACCESS_TOKEN')
        refresh_token = os.environ.get('GOOGLE_REFRESH_TOKEN')
        client_id = os.environ.get('GOOGLE_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        
        if not all([access_token, refresh_token, client_id, client_secret]):
            logger.error("Missing OAuth credentials in environment variables")
            return None
            
        # Create credentials
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri='https://oauth2.googleapis.com/token'
        )
        
        # Build service
        service = build('calendar', 'v3', credentials=creds)
        logger.info("Google Calendar service created successfully")
        return service
        
    except Exception as e:
        logger.error(f"Failed to create calendar service: {e}")
        return None

def get_calendar_id():
    """Get the calendar ID from environment"""
    return os.environ.get('GOOGLE_CALENDAR_ID', 'primary')


@app.get("/")
async def root():
    """Root endpoint - MCP server info for ElevenLabs compatibility"""
    return {
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Google Calendar MCP Server",
                "version": "1.0.0"
            }
        }
    }

@app.post("/")
async def root_post(request: dict):
    """Root endpoint POST handler for MCP requests"""
    logger.info(f"Received root POST request: {request}")
    logger.info(f"Request keys: {list(request.keys()) if request else 'No request'}")
    
    # ElevenLabs might expect a direct tools list response
    if not request or request == {}:
        logger.info("Empty request at root - returning tools list")
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": MCP_TOOLS
            }
        }
    
    method = request.get("method", "")
    logger.info(f"Root method: {method}")
    
    # Handle MCP initialization request
    if method == "initialize":
        logger.info("Returning initialization response")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id", 1),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "Google Calendar MCP Server",
                    "version": "1.0.0"
                }
            }
        }
    
    # Handle tool list requests
    elif method == "tools/list" or method == "list_tools":
        logger.info("Returning tools list")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id", 1),
            "result": {
                "tools": MCP_TOOLS
            }
        }
    
    # Handle tool calls
    elif method == "tools/call":
        logger.info("Handling tool call")
        return await call_tool(request)
    
    # Default response - include tools for ElevenLabs
    logger.info("Returning default response with tools")
    return {
        "jsonrpc": "2.0",
        "id": request.get("id", 1),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Google Calendar MCP Server",
                "version": "1.0.0"
            },
            "tools": MCP_TOOLS
        }
    }

@app.get("/health")
async def health():
    """Health check endpoint for Railway"""
    return "ok"

@app.get("/status")
async def status():
    """Detailed status endpoint"""
    service = get_calendar_service()
    return {
        "status": "running",
        "calendar_service_available": service is not None,
        "calendar_id": get_calendar_id(),
        "tools_count": len(MCP_TOOLS),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/mcp")
async def mcp_info():
    """MCP server information endpoint"""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Google Calendar MCP Server",
                "version": "1.0.0"
            }
        }
    }

@app.post("/mcp")
async def mcp_post(request: dict):
    """MCP endpoint POST handler for MCP requests"""
    logger.info(f"Received MCP POST request: {request}")
    
    # ElevenLabs might expect a direct tools list response
    if not request or request == {}:
        logger.info("Empty request - returning tools list")
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": MCP_TOOLS
            }
        }
    
    # Check if ElevenLabs is asking for capabilities
    method = request.get("method", "")
    logger.info(f"MCP method: {method}")
    
    if method == "tools/list" or method == "list_tools":
        logger.info("Returning tools list")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id", 1),
            "result": {
                "tools": MCP_TOOLS
            }
        }
    elif method == "initialize" or method == "init":
        logger.info("Returning initialization response")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id", 1),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "Google Calendar MCP Server",
                    "version": "1.0.0"
                }
            }
        }
    else:
        # Default: return both server info and tools
        logger.info("Returning combined response")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id", 1),
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "Google Calendar MCP Server",
                    "version": "1.0.0"
                },
                "tools": MCP_TOOLS
            }
        }

@app.get("/mcp/info")
async def mcp_info_alt():
    """Alternative MCP info endpoint for compatibility"""
    return {
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Google Calendar MCP Server",
                "version": "1.0.0"
            }
        }
    }

@app.get("/tools")
async def list_tools():
    """List available tools - returns OpenAI function format for ElevenLabs"""
    # Convert MCP tools to OpenAI function format
    openai_tools = []
    for tool in MCP_TOOLS:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"]
            }
        }
        openai_tools.append(openai_tool)
    
    return openai_tools

@app.get("/mcp/tools")
async def list_mcp_tools():
    """List available MCP tools in proper MCP format"""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": MCP_TOOLS
        }
    }

@app.post("/mcp/tools")
async def call_mcp_tool(request: dict):
    """Execute MCP tool calls via /mcp/tools endpoint"""
    return await call_tool(request)

@app.get("/elevenlabs/tools")
async def list_elevenlabs_tools():
    """List tools in ElevenLabs format"""
    return {
        "tools": MCP_TOOLS
    }

@app.get("/elevenlabs/webhook")
async def elevenlabs_webhook_info():
    """ElevenLabs webhook endpoint info (for verification)"""
    return {
        "status": "ready",
        "webhook_url": "/elevenlabs/webhook",
        "method": "POST",
        "description": "ElevenLabs webhook endpoint for agent tool calls"
    }

@app.post("/elevenlabs/webhook")
async def elevenlabs_webhook(request: dict):
    """ElevenLabs webhook endpoint for agent tool calls"""
    try:
        logger.info(f"Received ElevenLabs webhook: {request}")
        
        # Extract tool call from ElevenLabs request
        if "tool_calls" not in request:
            raise HTTPException(status_code=400, detail="No tool_calls in request")
        
        tool_calls = request["tool_calls"]
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name")
            tool_params = tool_call.get("function", {}).get("arguments", {})
            
            if not tool_name:
                continue
                
            # Get calendar service
            service = get_calendar_service()
            if not service:
                results.append({
                    "tool_call_id": tool_call.get("id"),
                    "error": "Google Calendar service not available"
                })
                continue
            
            # Route to appropriate tool handler
            try:
                if tool_name == "check_availability":
                    result = await check_availability(service, tool_params)
                elif tool_name == "book_appointment":
                    result = await book_appointment(service, tool_params)
                elif tool_name == "cancel_appointment":
                    result = await cancel_appointment(service, tool_params)
                elif tool_name == "reschedule_appointment":
                    result = await reschedule_appointment(service, tool_params)
                elif tool_name == "get_appointments":
                    result = await get_appointments(service, tool_params)
                elif tool_name == "find_next_available":
                    result = await find_next_available(service, tool_params)
                else:
                    result = f"Unknown tool: {tool_name}"
                
                results.append({
                    "tool_call_id": tool_call.get("id"),
                    "result": result
                })
                
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                results.append({
                    "tool_call_id": tool_call.get("id"),
                    "error": str(e)
                })
        
        return {"results": results}
        
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools")
async def call_tool(request: dict):
    """Execute tool calls - handles both MCP and ElevenLabs formats"""
    try:
        logger.info(f"Received tool call request: {request}")
        
        service = get_calendar_service()
        if not service:
            raise HTTPException(status_code=500, detail="Google Calendar service not available")
        
        # Handle MCP format
        if "jsonrpc" in request and "method" in request:
            tool_name = request["method"]
            params = request.get("params", {})
            request_id = request.get("id", 1)
            
            # Route to appropriate tool handler
            if tool_name == "check_availability":
                result = await check_availability(service, params)
            elif tool_name == "book_appointment":
                result = await book_appointment(service, params)
            elif tool_name == "cancel_appointment":
                result = await cancel_appointment(service, params)
            elif tool_name == "reschedule_appointment":
                result = await reschedule_appointment(service, params)
            elif tool_name == "get_appointments":
                result = await get_appointments(service, params)
            elif tool_name == "find_next_available":
                result = await find_next_available(service, params)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": result}]}
            }
        
        # Handle ElevenLabs format (tool_calls array)
        elif "tool_calls" in request:
            tool_calls = request["tool_calls"]
            results = []
            
            for tool_call in tool_calls:
                tool_name = tool_call.get("function", {}).get("name")
                tool_params = tool_call.get("function", {}).get("arguments", {})
                
                if not tool_name:
                    continue
                
                try:
                    if tool_name == "check_availability":
                        result = await check_availability(service, tool_params)
                    elif tool_name == "book_appointment":
                        result = await book_appointment(service, tool_params)
                    elif tool_name == "cancel_appointment":
                        result = await cancel_appointment(service, tool_params)
                    elif tool_name == "reschedule_appointment":
                        result = await reschedule_appointment(service, tool_params)
                    elif tool_name == "get_appointments":
                        result = await get_appointments(service, tool_params)
                    elif tool_name == "find_next_available":
                        result = await find_next_available(service, tool_params)
                    else:
                        result = f"Unknown tool: {tool_name}"
                    
                    results.append({
                        "tool_call_id": tool_call.get("id"),
                        "result": result
                    })
                    
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    results.append({
                        "tool_call_id": tool_call.get("id"),
                        "error": str(e)
                    })
            
            return {"results": results}
        
        else:
            raise HTTPException(status_code=400, detail="Invalid request format")
        
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return {
            "jsonrpc": "2.0", 
            "id": request.get("id", 1),
            "error": {"code": -32603, "message": str(e)}
        }

# Tool implementations
async def check_availability(service, params):
    """Check available appointment slots"""
    try:
        date = params['date']
        start_time = params['start_time']
        end_time = params['end_time']
        duration = params.get('duration', 60)
        
        # Parse datetime
        start_datetime = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_datetime = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        
        # Get existing events
        calendar_id = get_calendar_id()
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_datetime.isoformat() + 'Z',
            timeMax=end_datetime.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Find available slots
        available_slots = []
        current_time = start_datetime
        
        while current_time + timedelta(minutes=duration) <= end_datetime:
            slot_end = current_time + timedelta(minutes=duration)
            
            # Check if slot conflicts with existing event
            is_available = True
            for event in events:
                event_start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                event_end = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                
                if (current_time < event_end and slot_end > event_start):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append({
                    "time": current_time.strftime("%H:%M"),
                    "datetime": current_time.isoformat()
                })
            
            current_time += timedelta(minutes=30)  # Check every 30 minutes
        
        return f"Available {duration}-minute slots on {date}: {len(available_slots)} slots found\n" + \
               "\n".join([f"- {slot['time']}" for slot in available_slots])
               
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check availability: {e}")

async def book_appointment(service, params):
    """Book a new appointment"""
    try:
        date = params['date']
        time = params['time']
        duration = params.get('duration', 60)
        patient_name = params['patient_name']
        patient_email = params['patient_email']
        phone = params.get('phone', '')
        service_type = params['service']
        
        # Create datetime
        start_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_datetime = start_datetime + timedelta(minutes=duration)
        
        # Create event
        event = {
            'summary': f"Dental Appointment - {patient_name}",
            'description': f"Service: {service_type}\nPatient: {patient_name}\nPhone: {phone}",
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': [
                {'email': patient_email, 'displayName': patient_name}
            ]
        }
        
        calendar_id = get_calendar_id()
        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        
        return f"Appointment booked successfully!\n" + \
               f"Date: {date} at {time}\n" + \
               f"Patient: {patient_name}\n" + \
               f"Service: {service_type}\n" + \
               f"Duration: {duration} minutes\n" + \
               f"Event ID: {event_result['id']}"
               
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to book appointment: {e}")

async def cancel_appointment(service, params):
    """Cancel an appointment"""
    try:
        appointment_id = params['appointment_id']
        reason = params.get('reason', 'No reason provided')
        
        calendar_id = get_calendar_id()
        
        # Get event details first
        event = service.events().get(calendarId=calendar_id, eventId=appointment_id).execute()
        
        # Delete the event
        service.events().delete(calendarId=calendar_id, eventId=appointment_id).execute()
        
        return f"Appointment cancelled successfully!\n" + \
               f"Event: {event.get('summary', 'Unknown')}\n" + \
               f"Reason: {reason}"
               
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel appointment: {e}")

async def reschedule_appointment(service, params):
    """Reschedule an appointment"""
    try:
        appointment_id = params['appointment_id']
        new_date = params['new_date']
        new_time = params['new_time']
        duration = params.get('duration', 60)
        
        calendar_id = get_calendar_id()
        
        # Get existing event
        event = service.events().get(calendarId=calendar_id, eventId=appointment_id).execute()
        
        # Update datetime
        start_datetime = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        end_datetime = start_datetime + timedelta(minutes=duration)
        
        event['start']['dateTime'] = start_datetime.isoformat()
        event['end']['dateTime'] = end_datetime.isoformat()
        
        # Update event
        updated_event = service.events().update(
            calendarId=calendar_id, 
            eventId=appointment_id, 
            body=event
        ).execute()
        
        return f"Appointment rescheduled successfully!\n" + \
               f"New date: {new_date} at {new_time}\n" + \
               f"Duration: {duration} minutes\n" + \
               f"Event: {event.get('summary', 'Unknown')}"
               
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reschedule appointment: {e}")

async def get_appointments(service, params):
    """Get appointments for date range"""
    try:
        start_date = params['start_date']
        end_date = params['end_date']
        
        # Parse dates
        start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        end_datetime = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        
        calendar_id = get_calendar_id()
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_datetime.isoformat() + 'Z',
            timeMax=end_datetime.isoformat() + 'Z',
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"No appointments found between {start_date} and {end_date}"
        
        appointments = []
        for event in events:
            start_time = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
            appointments.append(
                f"- {start_time.strftime('%Y-%m-%d %H:%M')}: {event.get('summary', 'No title')} (ID: {event['id']})"
            )
        
        return f"Appointments from {start_date} to {end_date}:\n" + "\n".join(appointments)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get appointments: {e}")

async def find_next_available(service, params):
    """Find next available appointment slot"""
    try:
        duration = params.get('duration', 60)
        days_ahead = params.get('days_ahead', 30)
        
        # Search from tomorrow
        search_start = datetime.now() + timedelta(days=1)
        search_end = search_start + timedelta(days=days_ahead)
        
        # Business hours: 9 AM to 5 PM, Monday to Friday
        current_date = search_start.date()
        end_date = search_end.date()
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                # Check each hour from 9 AM to 4 PM (to allow for 1-hour appointments)
                for hour in range(9, 17 - (duration // 60)):
                    check_datetime = datetime.combine(current_date, datetime.min.time().replace(hour=hour))
                    
                    # Check if this slot is available
                    calendar_id = get_calendar_id()
                    events_result = service.events().list(
                        calendarId=calendar_id,
                        timeMin=check_datetime.isoformat() + 'Z',
                        timeMax=(check_datetime + timedelta(minutes=duration)).isoformat() + 'Z',
                        singleEvents=True
                    ).execute()
                    
                    events = events_result.get('items', [])
                    
                    if not events:  # Slot is available
                        return f"Next available {duration}-minute slot:\n" + \
                               f"Date: {current_date.strftime('%Y-%m-%d')}\n" + \
                               f"Time: {check_datetime.strftime('%H:%M')}\n" + \
                               f"Day: {current_date.strftime('%A')}"
            
            current_date += timedelta(days=1)
        
        return f"No available {duration}-minute slots found in the next {days_ahead} days"
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to find next available slot: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
