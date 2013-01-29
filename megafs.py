from megaclient import MegaClient
import errno
import fuse
import getpass
import os
import stat
import time

fuse.fuse_python_api = (0, 2)

class MegaFS(fuse.Fuse):
  def __init__(self, client, *args, **kw):
    fuse.Fuse.__init__(self, *args, **kw)
    self.client = client
    self.hash2path = {}
    self.files = {'/': {'t': 1, 'ts': int(time.time()), 'children': []}}

    self.client.login()
    files = self.client.getfiles()

    for file_h, file in files.items():
      path = self.getpath(files, file_h)
      dirname, basename = os.path.split(path)
      if not dirname in self.files:
        self.files[dirname] = {'children': []}
      self.files[dirname]['children'].append(basename)
      if path in self.files:
        self.files[path].update(file)
      else:
        self.files[path] = file
        if file['t'] > 0:
          self.files[path]['children'] = []

  def getpath(self, files, hash):
    if not hash:
      return ""
    elif not hash in self.hash2path:
      path = self.getpath(files, files[hash]['p']) + "/" + files[hash]['a']['n']

      i = 1
      filename, fileext = os.path.splitext(path)
      while path in self.hash2path.values():
        path = filename + ' (%d)' % i + fileext
        i += 1

      self.hash2path[hash] = path.encode()
    return self.hash2path[hash]

  def getattr(self, path):
    st = fuse.Stat()

    if path not in self.files:
      return -errno.ENOENT

    file = self.files[path]
    st.st_atime = file['ts']
    st.st_mtime = st.st_atime
    st.st_ctime = st.st_atime
    if file['t'] == 0:
      st.st_mode = stat.S_IFREG | 0666
      st.st_nlink = 1
      st.st_size = file['s']
    else:
      st.st_mode = stat.S_IFDIR | 0755
      st.st_nlink = 2 + len([child for child in file['children'] if self.files[os.path.join(path, child)]['t'] > 0])
      st.st_size = 4096
    return st

  def readdir(self, path, offset):
    dirents = ['.', '..'] + self.files[path]['children']
    for r in dirents:
      yield fuse.Direntry(r)

if __name__ == '__main__':
  email = raw_input("Email [%s]: " % getpass.getuser())
  if not email:
    email = getpass.getuser()
  password = getpass.getpass()
  client = MegaClient(email, password)
  fs = MegaFS(client)
  fs.parse(errex=1)
  fs.main()
