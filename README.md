# Google Calendar MCP Server

A Model Context Protocol (MCP) server for managing dental appointments through Google Calendar. Built specifically for Railway deployment with clean, production-ready code.

## Features

- **Appointment Management**: Book, cancel, and reschedule dental appointments
- **Availability Checking**: Check available time slots for specific dates
- **Calendar Integration**: Full Google Calendar API integration
- **MCP Protocol**: Compatible with MCP clients and AI assistants
- **Railway Ready**: Optimized for Railway deployment

## Available Tools

1. **check_availability** - Check available appointment slots for a specific date and time range
2. **book_appointment** - Book a new dental appointment
3. **cancel_appointment** - Cancel an existing appointment
4. **reschedule_appointment** - Reschedule an existing appointment
5. **get_appointments** - Get appointments for a specific date range
6. **find_next_available** - Find the next available appointment slot

## Setup

### Prerequisites

1. Google Cloud Console project with Calendar API enabled
2. OAuth 2.0 credentials configured
3. Python 3.11+ (for local development)

### Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Google Calendar API
4. Go to "Credentials" and create OAuth 2.0 Client ID
5. Configure OAuth consent screen
6. Download the credentials JSON file

### Environment Variables

Copy `env.example` to `.env` and fill in your credentials:

```bash
cp env.example .env
```

Required environment variables:
- `GOOGLE_CLIENT_ID` - Your Google OAuth client ID
- `GOOGLE_CLIENT_SECRET` - Your Google OAuth client secret
- `GOOGLE_ACCESS_TOKEN` - OAuth access token (obtained through OAuth flow)
- `GOOGLE_REFRESH_TOKEN` - OAuth refresh token (obtained through OAuth flow)
- `GOOGLE_CALENDAR_ID` - Calendar ID (use 'primary' for main calendar)
- `PORT` - Server port (default: 8000)

### OAuth Token Generation

To get the access and refresh tokens, you'll need to run the OAuth flow. Here's a simple script to help:

```python
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_credentials():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    print(f"Access Token: {creds.token}")
    print(f"Refresh Token: {creds.refresh_token}")
    print(f"Client ID: {creds.client_id}")
    print(f"Client Secret: {creds.client_secret}")

if __name__ == '__main__':
    get_credentials()
```

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables (see above)

3. Run the server:
```bash
python main.py
```

The server will be available at `http://localhost:8000`

## Railway Deployment

1. Connect your GitHub repository to Railway
2. Set the environment variables in Railway dashboard
3. Railway will automatically build and deploy using the Dockerfile

### Railway Environment Variables

Set these in your Railway project dashboard:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_ACCESS_TOKEN`
- `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_CALENDAR_ID` (optional, defaults to 'primary')

## API Endpoints

### Health Check
- `GET /health` - Simple health check
- `GET /status` - Detailed status with service availability

### MCP Tools
- `GET /tools` - List available tools
- `POST /tools` - Execute tool calls

### Example Tool Call

```bash
curl -X POST "https://your-railway-app.railway.app/tools" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "check_availability",
    "params": {
      "date": "2024-01-15",
      "start_time": "09:00",
      "end_time": "17:00",
      "duration": 60
    }
  }'
```

## Project Structure

```
dental-calendar-mcp-clean/
├── main.py              # Main FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
├── railway.json        # Railway deployment config
├── env.example         # Environment variables template
└── README.md           # This file
```

## Error Handling

The server includes comprehensive error handling:
- OAuth credential validation
- Google Calendar API error handling
- Input validation for all tool parameters
- Proper HTTP status codes and error messages

## Security Notes

- Never commit OAuth credentials to version control
- Use environment variables for all sensitive data
- The server includes CORS middleware for web integration
- All API endpoints are properly validated

## License

This project is open source and available under the MIT License.
