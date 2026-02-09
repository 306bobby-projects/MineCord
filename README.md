# Minecraft Server Manager

A comprehensive Minecraft server manager with Discord bot integration that supports multiple server instances, CurseForge modpack downloads, and automatic crash recovery.

## Features

- **Multiple Server Instances**: Manage multiple Minecraft servers simultaneously
- **Discord Bot Integration**: Control servers via Discord commands with role-based access
- **CurseForge Support**: Auto-download server packs from CurseForge modpack links
- **Daemon Mode**: Runs as a systemd service with auto-start on boot
- **Auto-Restart**: Automatically restarts servers that were running before reboot
- **Crash Detection**: Notifications when servers crash
- **Resource Limits**: Configurable concurrent server limits

## Requirements

- Python 3.8+
- Java (for Minecraft servers)
- Discord Bot Token

## Installation

```bash
# Clone the repository
git clone https://github.com/306bobby-projects/MineCord.git
cd MineCord

# Install dependencies
pip install -r requirements.txt

# Configure the bot
cp config.yaml.example config.yaml
# Edit config.yaml with your Discord bot token and settings

# Install systemd service (Linux)
sudo cp mc-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mc-manager
sudo systemctl start mc-manager
```

## GitHub

Repository: [https://github.com/306bobby-projects/MineCord](https://github.com/306bobby-projects/MineCord)

## Configuration

Edit `config.yaml` to configure:

```yaml
discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  required_role: "Minecraft Admin"  # Role required to use commands
  command_channel: "server-commands"
  log_channel: "server-logs"

servers:
  directory: "./servers"
  max_concurrent: 3  # Maximum concurrent running servers
  auto_start_on_boot: true
  default_memory: 4096  # Default JVM memory in MB
  crash_notification: true
  port_range:
    min: 25565  # Minimum port for server instances
    max: 25665  # Maximum port for server instances
```

## Discord Commands

| Command | Description |
|---------|-------------|
| `/create <name> <version\|url> [memory] [server_url]` | Create a new server |
| `/start <name>` | Start a server |
| `/stop <name>` | Stop a server |
| `/restart <name>` | Restart a server |
| `/delete <name>` | Delete a server and its files |
| `/console <name> <command>` | Send command to server console |
| `/setprop <name> <property> <value>` | Set a server.properties value |
| `/list` | List all servers and their status |
| `/status <name>` | Get detailed server status |
| `/help` | Show help message |

### Create Command Examples

```bash
# Create a vanilla server
/create myserver 1.20.1 4096

# Create from CurseForge modpack
/create atm10 https://www.curseforge.com/minecraft/modpacks/all-the-mods-10

# Create with custom server file URL
/create mymodpack https://www.curseforge.com/minecraft/modpacks/some-pack 8192 https://www.curseforge.com/minecraft/modpacks/some-pack/files/1234567
```

## Adding the Bot to Your Server

1. Create a Discord Application at https://discord.com/developers/applications
2. Create a Bot user
3. Copy the bot token to `config.yaml`
4. Generate an invite URL with appropriate permissions:
   ```
   https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=268435456&scope=bot
   ```
5. Create the required Discord roles and channels

## Managing the Service

```bash
# Start the service
sudo systemctl start mc-manager

# Stop the service
sudo systemctl stop mc-manager

# View logs
journalctl -u mc-manager -f

# Restart the service
sudo systemctl restart mc-manager
```

## Project Structure

```
MineCord/
├── config.yaml           # Configuration file
├── main.py               # Application entry point
├── server_manager.py     # Server management logic
├── discord_bot.py        # Discord bot integration
├── mc-manager.service   # Systemd service file
├── requirements.txt      # Python dependencies
└── servers/              # Server instances directory
```

## JVM Memory Configuration

The default JVM arguments are optimized for stability and performance:

```
-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 
-XX:+UnlockExperimentalVMOptions -XX:G1NewSizePercent=30 
-XX:G1MaxNewSizePercent=50 -XX:G1HeapRegionSize=8m 
-XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 
-XX:G1PauseIntervalMs=150 -XX:InitiatingHeapOccupancyPercent=15
```

Modify `config.yaml` to adjust these settings or the default memory allocation.

## Troubleshooting

1. **Bot not responding**: Check that the bot has proper permissions and the role name matches exactly
2. **Server creation fails**: Verify CurseForge links are accessible and contain server packs
3. **Servers not starting**: Check logs for Java errors and ensure sufficient system resources
4. **Connection issues**: Verify firewalls allow Minecraft ports (default 25565)
5. **Port conflicts**: Adjust the port_range in config.yaml if all ports in range are in use

## Managing Server Ports

The manager automatically allocates ports from the configured range. Use the `/status` command to see which port a server is using. You can modify server properties like:

```bash
# Change server port
/setprop myserver server-port 25570

# Allow flight mode
/setprop myserver allow-flight true

# Change max players
/setprop myserver max-players 20

# Change view distance
/setprop myserver view-distance 10
```

Note: Changes to server.properties require a server restart to take effect.

## License

MIT License
