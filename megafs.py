from megaclient import MegaClient
import errno
import fuse
import os
import stat
import time

fuse.fuse_python_api = (0, 2)

class MegaFS(fuse.Fuse):
  def __init__(self, *args, **kw):
    fuse.Fuse.__init__(self, *args, **kw)
    self.hash2path = {}
    self.tree = {}

    client = MegaClient()
    client.login('EMAIL', 'PASSWORD')
    files = client.getfiles()

    for file_h, file in files.items():
      (head, tail) = os.path.split(self.getpath(files, file['h']))
      t = self.tree
      if head:
        for part in head.split("/"):
          if not part in t:
            t[part] = {'children': {}}
          t = t[part]['children']

      if tail in t:
        t[tail].update(file)
      else:
        t[tail] = file
        if file['t'] > 0:
          t[tail]['children'] = {}

  def getpath(self, files, hash):
    if not hash in self.hash2path:
      if not files[hash]['p']:
        path = files[hash]['a']['n']
      else:
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

    if path == '/':
      st.st_atime = int(time.time())
      st.st_mtime = st.st_atime
      st.st_ctime = st.st_atime
      st.st_mode = stat.S_IFDIR | 0755
      st.st_nlink = 2
      st.st_size = 4096
      return st

    try:
      (head, tail) = os.path.split(path.strip("/"))
      t = self.tree
      if head:
        for part in head.split("/"):
          t = t[part]['children']
      file = t[tail]
    except KeyError:
      return -errno.ENOENT

    st.st_atime = file['ts']
    st.st_mtime = st.st_atime
    st.st_ctime = st.st_atime
    if file['t'] == 0:
      st.st_mode = stat.S_IFREG | 0666
      st.st_nlink = 1
      st.st_size = file['s']
    else:
      st.st_mode = stat.S_IFDIR | 0755
      st.st_nlink = 2
      st.st_size = 4096
    return st

  def readdir(self, path, offset):
    dirents = ['.', '..']
    if path == '/':
      dirents.extend(self.tree.keys())
    else:
      t = self.tree
      for part in path.strip("/").split("/"):
        t = t[part]['children']
      dirents.extend(t.keys())
    for r in dirents:
      yield fuse.Direntry(r)

if __name__ == '__main__':
  fs = MegaFS()
  fs.parse(errex=1)
  fs.main()
