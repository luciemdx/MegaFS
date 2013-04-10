from Crypto.Cipher import AES
from Crypto.Util import Counter
from Crypto.PublicKey import RSA
from megacrypto import prepare_key, stringhash, encrypt_key, decrypt_key, enc_attr, dec_attr, aes_cbc_encrypt_a32
from megautil import a32_to_str, str_to_a32, a32_to_base64, base64_to_a32, mpi2int, base64urlencode, base64urldecode, get_chunks
import binascii
import json
import os
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

    def processfile(self, file, users_keys):
        if file['t'] == 0 or file['t'] == 1:
            keys = dict(keypart.split(':',1) for keypart in file['k'].split('/'))
            uid = file['u']
            key = None
            if uid in keys :
                # normal file or folder
                key = decrypt_key(base64_to_a32( keys[uid] ), self.master_key)
            elif 'su' in file and 'sk' in file and ':' in file['k']:
                # Shared folder
                user_key = decrypt_key(base64_to_a32(file['sk']),self.master_key)
                key = decrypt_key(base64_to_a32(keys[file['h']]),user_key)
                if file['su'] not in users_keys :
                    users_keys[file['su']] = {}
                users_keys[file['su']][file['h']] = user_key
            elif file['u'] and file['u'] in users_keys :
                # Shared file
                for hkey in users_keys[file['u']] :
                    user_key = users_keys[file['u']][hkey]
                    if hkey in keys :
                        key = keys[hkey]
                        key = decrypt_key(base64_to_a32(key),user_key)
                        break
            if key is not None :
                if file['t'] == 0:
                    k = file['k'] = (key[0] ^ key[4], key[1] ^ key[5], key[2] ^ key[6], key[3] ^ key[7])
                    iv = file['iv'] = key[4:6] + (0, 0)
                    meta_mac = file['meta_mac'] = key[6:8]
                else:
                    k = file['k'] = key
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
        return file

    def init_sharedkeys(self,files,users_keys) :
        # Init shared keys that comes from shared folders that aren't shared anymore
        ok_dict = {}
        for ok_item in files['ok'] :
            user_key = decrypt_key(base64_to_a32(ok_item['k']),self.master_key)
            ok_dict[ok_item['h']] = user_key
        for s_item in files['s'] :
            if s_item['u'] not in users_keys :
                users_keys[s_item['u']] = {}
            if s_item['h'] in ok_dict :
                users_keys[s_item['u']][s_item['h']] = ok_dict[s_item['h']]

    def getfiles(self):
        files = self.api_req({'a': 'f', 'c': 1})
        files_dict = {}
        users_keys={}
        self.init_sharedkeys(files,users_keys)
        for file in files['f']:
            files_dict[file['h']] = self.processfile(file,users_keys)
        return files_dict

    def downloadfile(self, file, dest_path):
        dl_url = self.api_req({'a': 'g', 'g': 1, 'n': file['h']})['g']

        infile = urllib.urlopen(dl_url)
        outfile = open(dest_path, 'wb')
        decryptor = AES.new(a32_to_str(file['k']), AES.MODE_CTR, counter = Counter.new(128, initial_value = ((file['iv'][0] << 32) + file['iv'][1]) << 64))

        file_mac = [0, 0, 0, 0]
        for chunk_start, chunk_size in sorted(get_chunks(file['s']).items()):
            chunk = infile.read(chunk_size)
            chunk = decryptor.decrypt(chunk)
            outfile.write(chunk)

            chunk_mac = [file['iv'][0], file['iv'][1], file['iv'][0], file['iv'][1]]
            for i in xrange(0, len(chunk), 16):
                block = chunk[i:i+16]
                if len(block) % 16:
                    block += '\0' * (16 - (len(block) % 16))
                block = str_to_a32(block)
                chunk_mac = [chunk_mac[0] ^ block[0], chunk_mac[1] ^ block[1], chunk_mac[2] ^ block[2], chunk_mac[3] ^ block[3]]
                chunk_mac = aes_cbc_encrypt_a32(chunk_mac, file['k'])

            file_mac = [file_mac[0] ^ chunk_mac[0], file_mac[1] ^ chunk_mac[1], file_mac[2] ^ chunk_mac[2], file_mac[3] ^ chunk_mac[3]]
            file_mac = aes_cbc_encrypt_a32(file_mac, file['k'])

        outfile.close()
        infile.close()

        return (file_mac[0] ^ file_mac[1], file_mac[2] ^ file_mac[3]) == file['meta_mac']

    def uploadfile(self, src_path, target, filename):
        infile = open(src_path, 'rb')
        size = os.path.getsize(src_path)
        ul_url = self.api_req({'a': 'u', 's': size})['p']

        ul_key = [random.randint(0, 0xFFFFFFFF) for _ in xrange(6)]
        encryptor = AES.new(a32_to_str(ul_key[:4]), AES.MODE_CTR, counter = Counter.new(128, initial_value = ((ul_key[4] << 32) + ul_key[5]) << 64))

        file_mac = [0, 0, 0, 0]
        for chunk_start, chunk_size in sorted(get_chunks(size).items()):
            chunk = infile.read(chunk_size)

            chunk_mac = [ul_key[4], ul_key[5], ul_key[4], ul_key[5]]
            for i in xrange(0, len(chunk), 16):
                block = chunk[i:i+16]
                if len(block) % 16:
                    block += '\0' * (16 - len(block) % 16)
                block = str_to_a32(block)
                chunk_mac = [chunk_mac[0] ^ block[0], chunk_mac[1] ^ block[1], chunk_mac[2] ^ block[2], chunk_mac[3] ^ block[3]]
                chunk_mac = aes_cbc_encrypt_a32(chunk_mac, ul_key[:4])

            file_mac = [file_mac[0] ^ chunk_mac[0], file_mac[1] ^ chunk_mac[1], file_mac[2] ^ chunk_mac[2], file_mac[3] ^ chunk_mac[3]]
            file_mac = aes_cbc_encrypt_a32(file_mac, ul_key[:4])

            chunk = encryptor.encrypt(chunk)
            outfile = urllib.urlopen(ul_url + "/" + str(chunk_start), chunk)
            completion_handle = outfile.read()
            outfile.close()

        infile.close()

        meta_mac = (file_mac[0] ^ file_mac[1], file_mac[2] ^ file_mac[3])

        attributes = {'n': filename}
        enc_attributes = enc_attr(attributes, ul_key[:4])
        key = [ul_key[0] ^ ul_key[4], ul_key[1] ^ ul_key[5], ul_key[2] ^ meta_mac[0], ul_key[3] ^ meta_mac[1], ul_key[4], ul_key[5], meta_mac[0], meta_mac[1]]
        return self.api_req({'a': 'p', 't': target, 'n': [{'h': completion_handle, 't': 0, 'a': base64urlencode(enc_attributes), 'k': a32_to_base64(encrypt_key(key, self.master_key))}]})
