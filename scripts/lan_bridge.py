import socket
import select
import threading
import sys

def forward_connection(client_sock, target_host, target_port):
    try:
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        remote_sock.connect((target_host, target_port))

        sockets = [client_sock, remote_sock]
        while True:
            r, _, _ = select.select(sockets, [], sockets, 30)
            if not r:
                break
            for s in r:
                other = remote_sock if s is client_sock else client_sock
                data = s.recv(32768)
                if not data:
                    return
                other.sendall(data)
    except Exception:
        pass
    finally:
        try: client_sock.close()
        except Exception: pass
        try: remote_sock.close()
        except Exception: pass

def start_lan_bridge(listen_ip="0.0.0.0", listen_port=51888, target_host="127.0.0.1", target_port=51888):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((listen_ip, listen_port))
    server.listen(64)
    print(f"[*] GNDROiD LAN-to-Emulator Bridge active: {listen_ip}:{listen_port} -> {target_host}:{target_port}")

    while True:
        try:
            client, addr = server.accept()
            t = threading.Thread(target=forward_connection, args=(client, target_host, target_port), daemon=True)
            t.start()
        except Exception as e:
            print("Accept error:", e)
            break

if __name__ == "__main__":
    start_lan_bridge()
