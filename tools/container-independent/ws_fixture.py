import base64,json,os,socket,struct
class WebSocket:
 def __init__(self,port):
  self.s=socket.create_connection(('127.0.0.1',port),timeout=15); self.buf=b''
  key=base64.b64encode(os.urandom(16)).decode()
  self.s.sendall((f'GET /ws?client_id=independent-fixture-{port} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
  while b'\r\n\r\n' not in self.buf:self.buf+=self.s.recv(4096)
  head,self.buf=self.buf.split(b'\r\n\r\n',1)
  assert b'101 Switching Protocols' in head,head
 def exact(self,n):
  while len(self.buf)<n:
   v=self.s.recv(65536)
   if not v: raise EOFError
   self.buf+=v
  result,self.buf=self.buf[:n],self.buf[n:];return result
 def send(self,obj):
  raw=json.dumps(obj).encode();mask=os.urandom(4); n=len(raw)
  header=bytes([0x81,(0x80|n) if n<126 else 0xfe if n<65536 else 0xff])
  if n>=126:header+=struct.pack('!H' if n<65536 else '!Q',n)
  self.s.sendall(header+mask+bytes(v^mask[i%4] for i,v in enumerate(raw)))
 def recv(self):
  chunks=[]
  while True:
   a,b=self.exact(2);length=b&127
   if length==126:length=struct.unpack('!H',self.exact(2))[0]
   if length==127:length=struct.unpack('!Q',self.exact(8))[0]
   mask=self.exact(4) if b&128 else None
   raw=self.exact(length)
   if mask:raw=bytes(v^mask[i%4] for i,v in enumerate(raw))
   if a&15==8:raise EOFError(raw)
   if a&15==9:continue
   chunks.append(raw)
   if a&128:return json.loads(b''.join(chunks))
 def close(self):self.s.close()
