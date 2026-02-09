import asyncio
import logging
import os
import json
import time
import subprocess
import threading
import yaml
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List
from enum import Enum
import aiohttp
from bs4 import BeautifulSoup
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServerStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"
    ERROR = "error"

@dataclass
class ServerConfig:
    name: str
    version: str
    memory: int
    port: int = 25565
    modpack_url: Optional[str] = None
    server_file_url: Optional[str] = None
    status: str = ServerStatus.STOPPED.value
    pid: Optional[int] = None
    last_started: Optional[float] = None
    restart_count: int = 0
    crash_count: int = 0

class MinecraftServerManager:
    def __init__(self, config_path: str = "./config.yaml"):
        self.config_path = config_path
        self.config = self.load_config()
        self.servers: Dict[str, ServerConfig] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        self.console_outputs: Dict[str, asyncio.Queue] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.allocated_ports: Dict[int, str] = {}
        self.lock = asyncio.Lock()
        
        self.servers_dir = Path(self.config["servers"]["directory"])
        self.max_concurrent = self.config["servers"]["max_concurrent"]
        self.default_memory = self.config["servers"]["default_memory"]
        self.port_min = self.config["servers"]["port_range"]["min"]
        self.port_max = self.config["servers"]["port_range"]["max"]
        
        self.ensure_directories()
        self.load_server_states()

    def load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def ensure_directories(self):
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = Path(self.config["logging"]["file"]).parent
        logs_dir.mkdir(parents=True, exist_ok=True)

    def load_server_states(self):
        state_file = self.servers_dir / "server_states.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                states = json.load(f)
                for name, data in states.items():
                    server = ServerConfig(**data)
                    self.servers[name] = server
                    if server.status == ServerStatus.RUNNING.value:
                        self.allocated_ports[server.port] = name

    def save_server_states(self):
        state_file = self.servers_dir / "server_states.json"
        states = {name: asdict(server) for name, server in self.servers.items()}
        with open(state_file, 'w') as f:
            json.dump(states, f, indent=2)

    def allocate_port(self) -> Optional[int]:
        for port in range(self.port_min, self.port_max + 1):
            if port not in self.allocated_ports:
                return port
        return None

    def release_port(self, port: int):
        if port in self.allocated_ports:
            del self.allocated_ports[port]

    def update_server_properties(self, name: str, property_name: str, value: str) -> bool:
        if name not in self.servers:
            return False
        
        server_dir = self.servers_dir / name
        props_file = server_dir / "server.properties"
        
        if not props_file.exists():
            return False
        
        properties = {}
        with open(props_file, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    properties[key] = val
        
        properties[property_name] = value
        
        with open(props_file, 'w') as f:
            for key, val in properties.items():
                f.write(f"{key}={val}\n")
        
        return True

    async def create_server(self, name: str, version: str, memory: Optional[int] = None, 
                           modpack_url: Optional[str] = None) -> tuple:
        async with self.lock:
            if name in self.servers:
                return False, f"Server '{name}' already exists"
            
            if len([s for s in self.servers.values() if s.status == ServerStatus.RUNNING.value]) >= self.max_concurrent:
                return False, f"Maximum concurrent servers ({self.max_concurrent}) reached"
            
            port = self.allocate_port()
            if port is None:
                return False, "No available ports in configured range"
            
            mem = memory or self.default_memory
            server = ServerConfig(
                name=name,
                version=version,
                memory=mem,
                port=port,
                modpack_url=modpack_url,
                server_file_url=None
            )
            
            server_dir = self.servers_dir / name
            server_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                if modpack_url:
                    success, message = await self.download_curseforge_server(server_dir, modpack_url)
                    if not success:
                        self.release_port(port)
                        return False, f"{message}\n\nPlease run the command again with the direct server pack URL: /create {name} <server_file_url>"
                else:
                    await self.download_vanilla_server(server_dir, version)
                
                props_file = server_dir / "server.properties"
                if props_file.exists():
                    self.update_server_properties(name, "server-port", str(port))
                
                self.servers[name] = server
                self.allocated_ports[port] = name
                self.save_server_states()
                return True, f"Server '{name}' created successfully on port {port}"
            except Exception as e:
                logger.error(f"Failed to create server {name}: {e}")
                self.release_port(port)
                return False, f"Failed to create server: {str(e)}"

    async def download_curseforge_server(self, server_dir: Path, modpack_url: str) -> tuple:
        try:
            async with aiohttp.ClientSession() as session:
                download_url = await self.find_curseforge_serverpack(session, modpack_url)
                if not download_url:
                    return False, "Could not find server pack on CurseForge page"
                
                logger.info(f"Downloading server pack from {download_url}")
                async with session.get(download_url) as response:
                    if response.status != 200:
                        return False, f"Failed to download: HTTP {response.status}"
                    
                    content = await response.read()
                    archive_path = server_dir / "server.zip"
                    with open(archive_path, 'wb') as f:
                        f.write(content)
                
                import zipfile
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(server_dir)
                archive_path.unlink()
                
                return True, "Server pack downloaded and extracted"
        except Exception as e:
            logger.error(f"CurseForge download failed: {e}")
            return False, f"Download failed: {str(e)}"

    async def find_curseforge_serverpack(self, session: aiohttp.ClientSession, modpack_url: str) -> Optional[str]:
        try:
            async with session.get(modpack_url) as response:
                if response.status != 200:
                    return None
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                files_section = soup.find('section', {'id': 'files'})
                if files_section:
                    server_files = files_section.find_all('a', href=re.compile(r'/minecraft/modpacks/.*/files/\d+'))
                    for link in server_files:
                        href = link.get('href')
                        if href:
                            return f"https://www.curseforge.com{href}"
                return None
        except Exception as e:
            logger.error(f"Failed to find server pack: {e}")
            return None

    async def download_vanilla_server(self, server_dir: Path, version: str):
        server_url = f"https://launcher.mojang.com/v1/objects/{version}/server.jar"
        async with aiohttp.ClientSession() as session:
            async with session.get(server_url) as response:
                if response.status != 200:
                    raise Exception(f"Failed to download vanilla server: HTTP {response.status}")
                with open(server_dir / "server.jar", 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

    async def start_server(self, name: str) -> tuple:
        if name not in self.servers:
            return False, f"Server '{name}' does not exist"
        
        server = self.servers[name]
        if server.status == ServerStatus.RUNNING.value:
            return False, f"Server '{name}' is already running"
        
        server_dir = self.servers_dir / name
        java_path = self.config["jvm"]["java_path"]
        jvm_args = self.config["jvm"]["java_args"]
        memory = server.memory
        
        eula_path = server_dir / "eula.txt"
        if not eula_path.exists():
            with open(eula_path, 'w') as f:
                f.write("eula=true\n")
        
        start_cmd = f"{java_path} -Xmx{memory}M -Xms{memory}M {jvm_args} -jar server.jar nogui"
        
        env = os.environ.copy()
        env['AWT_HEADLESS'] = '1'
        
        process = await asyncio.create_subprocess_shell(
            start_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=server_dir,
            env=env
        )
        
        self.processes[name] = process
        self.console_outputs[name] = asyncio.Queue()
        server.pid = process.pid
        server.status = ServerStatus.STARTING.value
        server.last_started = time.time()
        self.save_server_states()
        
        self.monitoring_tasks[name] = asyncio.create_task(self.monitor_server(name))
        
        await asyncio.sleep(5)
        if process.returncode is not None:
            _, stderr = await process.communicate()
            server.status = ServerStatus.CRASHED.value
            server.crash_count += 1
            self.save_server_states()
            return False, f"Server failed to start: {stderr.decode()}"
        
        server.status = ServerStatus.RUNNING.value
        self.save_server_states()
        return True, f"Server '{name}' started"

    async def monitor_server(self, name: str):
        process = self.processes.get(name)
        if not process:
            return
        
        server = self.servers.get(name)
        if not server:
            return
        
        while True:
            if process.returncode is not None:
                server.status = ServerStatus.CRASHED.value
                server.crash_count += 1
                self.save_server_states()
                await self.notify_crash(name)
                break
            
            await asyncio.sleep(self.config["monitoring"]["check_interval"])

    async def notify_crash(self, name: str):
        server = self.servers.get(name)
        if server and self.config["servers"]["crash_notification"]:
            return f"Server '{name}' crashed! Crash count: {server.crash_count}"
        return None

    async def stop_server(self, name: str) -> tuple:
        if name not in self.servers:
            return False, f"Server '{name}' does not exist"
        
        server = self.servers[name]
        if server.status != ServerStatus.RUNNING.value:
            return False, f"Server '{name}' is not running"
        
        process = self.processes.get(name)
        if process:
            process.terminate()
            try:
                await asyncio.sleep(1)
                if process.returncode is None:
                    process.kill()
                    process.wait()
            except Exception:
                pass
        
        server.status = ServerStatus.STOPPED.value
        server.pid = None
        self.save_server_states()
        return True, f"Server '{name}' stopped"

    async def restart_server(self, name: str) -> tuple:
        stopped, msg = await self.stop_server(name)
        if not stopped:
            return False, msg
        await asyncio.sleep(5)
        return await self.start_server(name)

    async def delete_server(self, name: str) -> tuple:
        if name not in self.servers:
            return False, f"Server '{name}' does not exist"
        
        server = self.servers[name]
        if server.status == ServerStatus.RUNNING.value:
            await self.stop_server(name)
        
        if name in self.processes:
            del self.processes[name]
        if name in self.console_outputs:
            del self.console_outputs[name]
        if name in self.monitoring_tasks:
            self.monitoring_tasks[name].cancel()
            del self.monitoring_tasks[name]
        
        server_dir = self.servers_dir / name
        if server_dir.exists():
            import shutil
            shutil.rmtree(server_dir)
        
        self.release_port(server.port)
        del self.servers[name]
        self.save_server_states()
        return True, f"Server '{name}' deleted"

    async def send_console_command(self, name: str, command: str) -> tuple:
        if name not in self.servers:
            return False, f"Server '{name}' does not exist"
        
        server = self.servers[name]
        process = self.processes.get(name)
        if not process or server.status != ServerStatus.RUNNING.value:
            return False, f"Server '{name}' is not running"
        
        try:
            if process.stdin:
                process.stdin.write(command + "\n")
                if hasattr(process.stdin, 'drain') and asyncio.iscoroutinefunction(getattr(process.stdin, 'drain', None)):
                    await process.stdin.drain()
            return True, f"Command sent to '{name}'"
        except Exception as e:
            return False, f"Failed to send command: {str(e)}"

    def get_running_count(self) -> int:
        return len([s for s in self.servers.values() if s.status == ServerStatus.RUNNING.value])

    async def auto_start_on_boot(self):
        if not self.config["servers"]["auto_start_on_boot"]:
            return
        
        for name, server in self.servers.items():
            if server.status == ServerStatus.RUNNING.value:
                logger.info(f"Auto-starting server {name} on boot")
                await self.start_server(name)

    async def cleanup(self):
        for name, task in self.monitoring_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        for name, process in self.processes.items():
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.sleep(1)
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                except Exception:
                    pass
