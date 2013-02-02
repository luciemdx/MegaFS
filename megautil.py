import base64
import binascii
import struct

def base64urldecode(data):
  data += '=='[(2 - len(data) * 3) % 4:]
  for search, replace in (('-', '+'), ('_', '/'), (',', '')):
    data = data.replace(search, replace)
  return base64.b64decode(data)

def base64urlencode(data):
  data = base64.b64encode(data)
  for search, replace in (('+', '-'), ('/', '_'), ('=', '')):
    data = data.replace(search, replace)
  return data

def a32_to_str(a):
  return struct.pack('>%dI' % len(a), *a)

def str_to_a32(b):
  if len(b) % 4:
    b += '\0' * (4 - len(b) % 4)
  return struct.unpack('>%dI' % (len(b) / 4), b)

def a32_to_base64(a):
  return base64urlencode(a32_to_str(a))

def base64_to_a32(s):
  return str_to_a32(base64urldecode(s))

def mpi2int(s):
  return int(binascii.hexlify(s[2:]), 16)

def get_chunks(size):
  chunks = {}
  p = pp = 0
  i = 1

  while i <= 8 and p < size - i * 0x20000:
    chunks[p] = i * 0x20000
    pp = p
    p += chunks[p]
    i += 1

  while p < size:
    chunks[p] = 0x100000
    pp = p
    p += chunks[p]

  chunks[pp] = size - pp
  if not chunks[pp]:
    del chunks[pp]

  return chunks
