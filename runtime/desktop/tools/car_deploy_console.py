"""Bounded SSH transport used only for the separate demo service."""
import time

def run(client,command,*,root=False,timeout=20):
    stdin,out,err=client.exec_command(('sudo -S -p "" -- ' if root else '')+command,timeout=timeout)
    if root:stdin.write('xilinx\n');stdin.flush()
    stdin.channel.shutdown_write();channel=out.channel;end=time.monotonic()+timeout;a=bytearray();b=bytearray()
    while True:
        while channel.recv_ready():a.extend(channel.recv(65536))
        while channel.recv_stderr_ready():b.extend(channel.recv_stderr(65536))
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
        if time.monotonic()>end:channel.close();raise TimeoutError('bounded remote command timed out')
        time.sleep(.02)
    result={'code':channel.recv_exit_status(),'stdout':a.decode('utf8','replace'),'stderr':b.decode('utf8','replace')}
    return result

if __name__=="__main__":raise SystemExit("请按普通电机版 README 部署本独立包；此工具不部署原编码器版本。")
