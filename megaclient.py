from Crypto.PublicKey import RSA
from megacrypto import prepare_key, stringhash, decrypt_key, dec_attr
from megautil import a32_to_str, str_to_a32, a32_to_base64, base64_to_a32, mpi2int, base64urlencode, base64urldecode
import binascii
import json
import random
import urllib

class MegaClient:
  def __init__(self, email, password):
    self.seqno = random.randint(0, 0xFFFFFFFF)
    self.sid = ''
    self.email = email
    self.password = password

  def api_req(self, req):
    url = 'https://g.api.mega.co.nz/cs?id=%d%s' % (self.seqno, '&sid=%s' % self.sid if self.sid else '')
    self.seqno += 1
    return json.loads(self.post(url, json.dumps([req])))[0]

  def post(self, url, data):
    return urllib.urlopen(url, data).read()

  def login(self):
    password_aes = prepare_key(str_to_a32(self.password))
    del self.password
    uh = stringhash(self.email.lower(), password_aes)
    res = self.api_req({'a': 'us', 'user': self.email, 'uh': uh})

    enc_master_key = base64_to_a32(res['k'])
    self.master_key = decrypt_key(enc_master_key, password_aes)
    if 'tsid' in res:
      tsid = base64urldecode(res['tsid'])
      if a32_to_str(encrypt_key(str_to_a32(tsid[:16]), self.master_key)) == tsid[-16:]:
        self.sid = res['tsid']
    elif 'csid' in res:
      enc_rsa_priv_key = base64_to_a32(res['privk'])
      rsa_priv_key = decrypt_key(enc_rsa_priv_key, self.master_key)

      privk = a32_to_str(rsa_priv_key)
      self.rsa_priv_key = [0, 0, 0, 0]

      for i in xrange(4):
        l = ((ord(privk[0]) * 256 + ord(privk[1]) + 7) / 8) + 2
        self.rsa_priv_key[i] = mpi2int(privk[:l])
        privk = privk[l:]

      enc_sid = mpi2int(base64urldecode(res['csid']))
      decrypter = RSA.construct((self.rsa_priv_key[0] * self.rsa_priv_key[1], 0L, self.rsa_priv_key[2], self.rsa_priv_key[0], self.rsa_priv_key[1]))
      sid = '%x' % decrypter.key._decrypt(enc_sid)
      sid = binascii.unhexlify('0' + sid if len(sid) % 2 else sid)
      self.sid = base64urlencode(sid[:43])

  def getfiles(self):
    files = self.api_req({'a': 'f', 'c': 1})
    files_dict = {}
    for file in files['f']:
      if file['t'] == 0 or file['t'] == 1:
        key = file['k'][file['k'].index(':') + 1:]
        key = decrypt_key(base64_to_a32(key), self.master_key)
        if file['t'] == 0:
          k = (key[0] ^ key[4], key[1] ^ key[5], key[2] ^ key[6], key[3] ^ key[7])
          iv = key[4:6] + (0, 0)
          meta_mac = key[6:8]
        else:
          k = key
        attributes = base64urldecode(file['a'])
        attributes = dec_attr(attributes, k)
        file['a'] = attributes
      elif file['t'] == 2:
        self.root_id = file['h']
        file['a'] = {'n': 'Cloud Drive'}
      elif file['t'] == 3:
        self.inbox_id = file['h']
        file['a'] = {'n': 'Inbox'}
      elif file['t'] == 4:
        self.trashbin_id = file['h']
        file['a'] = {'n': 'Rubbish Bin'}
      files_dict[file['h']] = file
    return files_dict
