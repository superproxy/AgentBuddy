import paramiko
import socket

host = '123.60.75.27'
port = 22
user = 'root'
password = 'asdf062516!!!!'

# 1. TCP 连接测试
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    result = s.connect_ex((host, port))
    if result == 0:
        print(f"TCP port {port}: OPEN")
    else:
        print(f"TCP port {port}: CLOSED (err={result})")
    s.close()
except Exception as e:
    print(f"TCP error: {e}")

# 2. SSH 连接
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=30, banner_timeout=30)
    stdin, stdout, stderr = ssh.exec_command('echo OK && python3 --version && uname -a && df -h / && free -h')
    out = stdout.read().decode()
    err = stderr.read().decode()
    print("=== STDOUT ===")
    print(out)
    if err:
        print("=== STDERR ===")
        print(err)
    ssh.close()
    print("=== SSH OK ===")
except Exception as e:
    print(f"SSH error: {e}")
