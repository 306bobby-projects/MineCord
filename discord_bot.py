import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from typing import Optional
from server_manager import MinecraftServerManager, ServerStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MinecraftBot(commands.Cog):
    def __init__(self, bot, server_manager: MinecraftServerManager, config: dict):
        self.bot = bot
        self.server_manager = server_manager
        self.config = config
        self.required_role = config["discord"]["required_role"]
        self.command_channel = config["discord"]["command_channel"]
        self.log_channel = config["discord"]["log_channel"]

    def has_required_role(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        role = discord.utils.get(interaction.guild.roles, name=self.required_role)
        if not role:
            return False
        return role in interaction.user.roles

    async def send_log(self, message: str):
        channel = discord.utils.get(self.bot.get_all_channels(), name=self.log_channel)
        if channel:
            try:
                await channel.send(message)
            except Exception as e:
                logger.error(f"Failed to send log: {e}")

    @app_commands.command(name="create", description="Create a new Minecraft server instance")
    @app_commands.describe(
        name="Unique name for the server",
        version_or_url="Minecraft version or CurseForge modpack URL",
        memory="JVM memory allocation in MB (optional)"
    )
    async def create_server(self, interaction: discord.Interaction, name: str, version_or_url: str, 
                           memory: Optional[int] = None):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if not name.isalnum():
            await interaction.response.send_message("❌ Server name must be alphanumeric.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        is_url = version_or_url.startswith("http://") or version_or_url.startswith("https://")
        
        if is_url:
            success, message = await self.server_manager.create_server(
                name, 
                "modpack", 
                memory, 
                version_or_url
            )
        else:
            success, message = await self.server_manager.create_server(
                name,
                version_or_url,
                memory
            )

        if success:
            await interaction.followup.send(f"✅ {message}")
            await self.send_log(f"Server '{name}' created")
        else:
            await interaction.followup.send(f"❌ {message}")

    @app_commands.command(name="start", description="Start a Minecraft server instance")
    @app_commands.describe(name="Name of the server to start")
    async def start_server(self, interaction: discord.Interaction, name: str):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        success, message = await self.server_manager.start_server(name)
        if success:
            await interaction.response.send_message(f"✅ {message}")
            await self.send_log(f"Server '{name}' started")
        else:
            await interaction.response.send_message(f"❌ {message}")

    @app_commands.command(name="stop", description="Stop a Minecraft server instance")
    @app_commands.describe(name="Name of the server to stop")
    async def stop_server(self, interaction: discord.Interaction, name: str):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        success, message = await self.server_manager.stop_server(name)
        if success:
            await interaction.response.send_message(f"✅ {message}")
            await self.send_log(f"Server '{name}' stopped")
        else:
            await interaction.response.send_message(f"❌ {message}")

    @app_commands.command(name="restart", description="Restart a Minecraft server instance")
    @app_commands.describe(name="Name of the server to restart")
    async def restart_server(self, interaction: discord.Interaction, name: str):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        success, message = await self.server_manager.restart_server(name)
        if success:
            await interaction.response.send_message(f"✅ {message}")
            await self.send_log(f"Server '{name}' restarted")
        else:
            await interaction.response.send_message(f"❌ {message}")

    @app_commands.command(name="delete", description="Delete a Minecraft server instance")
    @app_commands.describe(name="Name of the server to delete")
    async def delete_server(self, interaction: discord.Interaction, name: str):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        success, message = await self.server_manager.delete_server(name)
        if success:
            await interaction.response.send_message(f"✅ {message}")
            await self.send_log(f"Server '{name}' deleted")
        else:
            await interaction.response.send_message(f"❌ {message}")

    @app_commands.command(name="console", description="Send a command to a Minecraft server console")
    @app_commands.describe(
        name="Name of the server",
        command="Command to send to the console"
    )
    async def send_console(self, interaction: discord.Interaction, name: str, command: str):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        success, message = await self.server_manager.send_console_command(name, command)
        if success:
            await interaction.response.send_message(f"✅ Command sent to '{name}': {command}")
        else:
            await interaction.response.send_message(f"❌ {message}")

    @app_commands.command(name="list", description="List all Minecraft servers")
    async def list_servers(self, interaction: discord.Interaction):
        servers = self.server_manager.servers
        if not servers:
            await interaction.response.send_message("No servers configured.")
            return

        running_count = self.server_manager.get_running_count()
        max_concurrent = self.server_manager.max_concurrent
        
        embed = discord.Embed(title="Minecraft Servers", color=discord.Color.blue())
        
        for name, server in servers.items():
            status_emoji = {
                ServerStatus.RUNNING.value: "🟢",
                ServerStatus.STOPPED.value: "🔴",
                ServerStatus.STARTING.value: "🟡",
                ServerStatus.STOPPING.value: "🟡",
                ServerStatus.CRASHED.value: "⚠️",
                ServerStatus.ERROR.value: "❌"
            }.get(server.status, "❓")

            embed.add_field(
                name=f"{status_emoji} {name}",
                value=f"Status: {server.status}\nVersion: {server.version}\nPort: {server.port}\nMemory: {server.memory}MB\nCrashes: {server.crash_count}",
                inline=True
            )

        embed.set_footer(text=f"Running: {running_count}/{max_concurrent} servers")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="status", description="Get detailed status of a server")
    @app_commands.describe(name="Name of the server")
    async def server_status(self, interaction: discord.Interaction, name: str):
        if name not in self.server_manager.servers:
            await interaction.response.send_message(f"❌ Server '{name}' does not exist.", ephemeral=True)
            return

        server = self.server_manager.servers[name]
        embed = discord.Embed(title=f"Server Status: {name}", color=discord.Color.green())
        
        uptime = "N/A"
        if server.last_started:
            uptime_seconds = int(__import__('time').time() - server.last_started)
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime = f"{hours}h {minutes}m {seconds}s"

        embed.add_field(name="Status", value=server.status, inline=True)
        embed.add_field(name="Version", value=server.version, inline=True)
        embed.add_field(name="Port", value=str(server.port), inline=True)
        embed.add_field(name="Memory", value=f"{server.memory}MB", inline=True)
        embed.add_field(name="Uptime", value=uptime, inline=True)
        embed.add_field(name="PID", value=str(server.pid) if server.pid else "N/A", inline=True)
        embed.add_field(name="Crash Count", value=str(server.crash_count), inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setprop", description="Set a server.properties value")
    @app_commands.describe(
        name="Name of the server",
        property="Property name to set",
        value="Value to set"
    )
    async def set_property(self, interaction: discord.Interaction, name: str, property: str, value: str):
        if not self.has_required_role(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if name not in self.server_manager.servers:
            await interaction.response.send_message(f"❌ Server '{name}' does not exist.", ephemeral=True)
            return

        success = self.server_manager.update_server_properties(name, property, value)
        if success:
            await interaction.response.send_message(f"✅ Set {property}={value} for server '{name}'. Restart required to apply.")
        else:
            await interaction.response.send_message(f"❌ Failed to update server.properties. Make sure the file exists.", ephemeral=True)

class MinecraftServerBot:
    def __init__(self, server_manager: MinecraftServerManager, config_path: str = "./config.yaml"):
        self.server_manager = server_manager
        self.config_path = config_path
        self.config = self.load_config()
        
        intents = discord.Intents.default()
        intents.message_content = True
        
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        self.cog = MinecraftBot(self.bot, self.server_manager, self.config)
        self.bot.add_cog(self.cog)

    def load_config(self):
        import yaml
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    async def run(self):
        token = self.config["discord"]["token"]
        if not token or token == "YOUR_DISCORD_BOT_TOKEN":
            logger.error("Discord bot token not configured!")
            return

        @self.bot.event
        async def on_ready():
            logger.info(f"Bot logged in as {self.bot.user}")
            try:
                synced = await self.bot.tree.sync()
                logger.info(f"Synced {len(synced)} slash commands")
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")
            await self.server_manager.auto_start_on_boot()

        @self.bot.event
        async def on_command_error(ctx, error):
            logger.error(f"Command error: {error}")
            try:
                await ctx.send(f"Error: {str(error)}")
            except:
                pass

        await self.bot.start(token)

    async def shutdown(self):
        await self.server_manager.cleanup()
        await self.bot.close()
