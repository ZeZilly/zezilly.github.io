# MCP YouTube Server Setup Task - COMPLETED

## Goal
Set up the MCP server from https://github.com/anaisbetts/mcp-youtube while following installation best practices.

## Steps
- [x] Load MCP documentation for installation guidelines
- [x] Check existing cline_mcp_settings.json to avoid overwriting existing servers (found existing servers, preserved them)
- [x] Install yt-dlp (required dependency for the YouTube MCP server) - via Homebrew
- [x] Create directory for the new MCP server
- [x] Install mcp-installer
- [x] Clone the mcp-youtube repository manually
- [x] Install dependencies with bun
- [x] Build the project successfully
- [x] Configure the server in cline_mcp_settings.json with server name "github.com/anaisbetts/mcp-youtube"
- [x] Verify the YouTube MCP server installation
- [x] Examine source code to understand available tools

## Server Configuration Added
```json
"github.com/anaisbetts/mcp-youtube": {
  "command": "node",
  "args": ["/Users/z-mac/Documents/Cline/MCP/mcp-youtube/dist/index.js"],
  "type": "stdio",
  "disabled": false,
  "autoApprove": []
}
```

## Available Tools
The MCP YouTube server provides one main tool:
- **download_youtube_url**: Downloads YouTube subtitles from a URL and processes them to extract readable content

## Dependencies Installed
- ✅ yt-dlp (via Homebrew) - located at /opt/homebrew/bin/yt-dlp
- ✅ bun (via npm) - for building the TypeScript project
- ✅ mcp-installer (via npm) - for MCP server management

## Installation Summary
All requirements have been met and the MCP YouTube server is now configured and ready to use. The server can download and process YouTube video subtitles, making them readable for Claude.
