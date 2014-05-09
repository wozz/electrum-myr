#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@ecdsa.org
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import threading, time, Queue, os, sys, shutil
from util import user_dir, appdata_dir, print_error, print_msg
from bitcoin import *
import hashlib
import sqlite3

try:
    from ltc_scrypt import getPoWHash as getPoWScryptHash
except ImportError:
    print_msg("Warning: ltc_scrypt not available, using fallback")
    from scrypt import scrypt_1024_1_1_80 as getPoWScryptHash

try:
    from groestl_hash import getPoWHash as getPoWGroestlHash
except ImportError:
    print_msg("Warning: groestl_hash not available, please install it")
    raise

try:
    from qubit_hash import getPoWHash as getPoWQubitHash
except ImportError:
    print_msg("Warning: qubit_hash not available, please install it")
    raise

try:
    from skeinhash import getPoWHash as getPoWSkeinHash
except ImportError:
    print_msg("Warning: skeinhash not available, please install it")
    raise


class Blockchain(threading.Thread):

    def __init__(self, config, network):
        threading.Thread.__init__(self)
        self.daemon = True
        self.config = config
        self.network = network
        self.lock = threading.Lock()
        self.local_height = 0
        self.running = False
        self.headers_url = 'http://myr.electr.us/blockchain_headers'
        self.set_local_height()
        self.queue = Queue.Queue()
        header_db_file = sqlite3.connect(self.db_path())
        header_db = header_db_file.cursor()
        try:
            first_header = header_db.execute('SELECT * FROM headers WHERE height = 0')
        except Exception:
            header_db.execute('CREATE TABLE headers (header, algo, height int UNIQUE)')
        header_db_file.commit()
        header_db_file.close()

    
    def height(self):
        return self.local_height


    def stop(self):
        with self.lock: self.running = False


    def is_running(self):
        with self.lock: return self.running


    def run(self):
        self.init_headers_file()
        self.set_local_height()
        print_error( "blocks:", self.local_height )

        with self.lock:
            self.running = True

        while self.is_running():

            try:
                result = self.queue.get()
            except Queue.Empty:
                continue

            if not result: continue

            i, header = result
            if not header: continue
            
            height = header.get('block_height')

            if height <= self.local_height:
                continue

            if height > self.local_height + 50:
                if not self.get_and_verify_chunks(i, header, height):
                    continue

            if height > self.local_height:
                # get missing parts from interface (until it connects to my chain)
                chain = self.get_chain( i, header )

                # skip that server if the result is not consistent
                if not chain: 
                    print_error('e')
                    continue
                
                # verify the chain
                if self.verify_chain( chain ):
                    print_error("height:", height, i.server)
                    for header in chain:
                        self.save_header(header)
                else:
                    print_error("error", i.server)
                    # todo: dismiss that server
                    continue


            self.network.new_blockchain_height(height, i)


                    
            
    def verify_chain(self, chain):

        first_header = chain[0]
        prev_header = self.read_header(first_header.get('block_height') -1)
        
        for header in chain:

            height = header.get('block_height')

            prev_hash = self.hash_header(prev_header)
            bits, target = self.get_target(height, chain)
            version = header.get('version')
            if version == 2:
                _hash = self.pow_hash_sha_header(header)
            elif version == 514:
                _hash = self.pow_hash_scrypt_header(header)
            elif version == 1026:
                _hash = self.pow_hash_groestl_header(header)
            elif version == 1538:
                _hash = self.pow_hash_skein_header(header)
            elif version == 2050:
                _hash = self.pow_hash_qubit_header(header)
            else:
                print_error( "error unknown block version")
            try:
                assert prev_hash == header.get('prev_block_hash')
                assert bits == header.get('bits')
                assert int('0x'+_hash,16) < target
            except Exception:
                return False

            prev_header = header

        return True



    def verify_chunk(self, index, hexdata):
        data = hexdata.decode('hex')
        height = index*2016
        num = len(data)/80

        if index == 0:  
            previous_hash = ("0"*64)
        else:
            prev_header = self.read_header(height-1)
            if prev_header is None: raise
            previous_hash = self.hash_header(prev_header)

        bits, target = self.get_target(height, data=data)

        for i in xrange(num):
            height = index*2016 + i
            bits, target = self.get_target(height, data=data)
            raw_header = data[i*80:(i+1)*80]
            header = self.header_from_string(raw_header)
            version = header.get('version')
            if version == 2:
                _hash = self.pow_hash_sha_header(header)
            elif version == 514:
                _hash = self.pow_hash_scrypt_header(header)
            elif version == 1026:
                _hash = self.pow_hash_groestl_header(header)
            elif version == 1538:
                _hash = self.pow_hash_skein_header(header)
            elif version == 2050:
                _hash = self.pow_hash_qubit_header(header)
            else:
                print_error( "error unknown block version")
            assert previous_hash == header.get('prev_block_hash')
            assert bits == header.get('bits')
            assert int('0x'+_hash,16) < target

            previous_header = header
            previous_hash = self.hash_header(header)

        self.save_chunk(index, data)
        print_error("validated chunk %d"%height)

        

    def header_to_string(self, res):
        s = int_to_hex(res.get('version'),4) \
            + rev_hex(res.get('prev_block_hash')) \
            + rev_hex(res.get('merkle_root')) \
            + int_to_hex(int(res.get('timestamp')),4) \
            + int_to_hex(int(res.get('bits')),4) \
            + int_to_hex(int(res.get('nonce')),4)
        return s


    def header_from_string(self, s):
        hex_to_int = lambda s: int('0x' + s[::-1].encode('hex'), 16)
        h = {}
        h['version'] = hex_to_int(s[0:4])
        h['prev_block_hash'] = hash_encode(s[4:36])
        h['merkle_root'] = hash_encode(s[36:68])
        h['timestamp'] = hex_to_int(s[68:72])
        h['bits'] = hex_to_int(s[72:76])
        h['nonce'] = hex_to_int(s[76:80])
        return h

    def hash_header(self, header):
        return rev_hex(Hash(self.header_to_string(header).decode('hex')).encode('hex'))

    def pow_hash_scrypt_header(self, header):
        return rev_hex(getPoWScryptHash(self.header_to_string(header).decode('hex')).encode('hex'))

    def pow_hash_sha_header(self,header):
        return self.hash_header(header)

    def pow_hash_skein_header(self,header):
        return rev_hex(getPoWSkeinHash(self.header_to_string(header).decode('hex')).encode('hex'))

    def pow_hash_groestl_header(self,header):
        return rev_hex(getPoWGroestlHash(self.header_to_string(header).decode('hex')).encode('hex'))

    def pow_hash_qubit_header(self,header):
        return rev_hex(getPoWQubitHash(self.header_to_string(header).decode('hex')).encode('hex'))

    def path(self):
        return os.path.join( self.config.path, 'blockchain_headers')
    
    def db_path(self):
        return os.path.join(self.config.path, 'headers.db')


    def init_headers_file(self):
        filename = self.path()
        if os.path.exists(filename):
            return
        
        try:
            import urllib, socket
            socket.setdefaulttimeout(30)
            print_error("downloading ", self.headers_url )
            urllib.urlretrieve(self.headers_url, filename)
            print_error("done.")
        except Exception:
            print_error( "download failed. creating file", filename )
            open(filename,'wb+').close()

    def save_chunk(self, index, chunk):
        filename = self.path()
        f = open(filename,'rb+')
        f.seek(index*2016*80)
        h = f.write(chunk)
        f.close()
        self.set_local_height()

    def save_header(self, header):
        data = self.header_to_string(header).decode('hex')
        assert len(data) == 80
        height = header.get('block_height')
        filename = self.path()
        f = open(filename,'rb+')
        f.seek(height*80)
        h = f.write(data)
        f.close()
        self.set_local_height()


    def set_local_height(self):
        name = self.path()
        if os.path.exists(name):
            h = os.path.getsize(name)/80 - 1
            if self.local_height != h:
                self.local_height = h


    def read_header(self, block_height):
        name = self.path()
        if os.path.exists(name):
            f = open(name,'rb')
            f.seek(block_height*80)
            h = f.read(80)
            f.close()
            if len(h) == 80:
                h = self.header_from_string(h)
                return h 


    def get_target(self, height, chain=[], data=None):

        header_db_file = sqlite3.connect(self.db_path())
        header_db = header_db_file.cursor()
        max_target = 0x00000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
        if height == 0 and data: 
            header_db.execute('''INSERT OR REPLACE INTO headers VALUES ('%s', '%s', '%s')''' % (data[0:80].encode('hex'), str(2), str(0)))
            header_db_file.commit()
            header_db_file.close()
        if height == 0: return 0x1e0fffff, 0x00000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

        # Myriadcoin
        if height < 10:
            first = self.read_header(0)
        else:
            first = self.read_header(height-10)
        last = self.read_header(height-1)

        if not data and chain:
            for h in chain:
                if h.get('block_height') == height:
                    last = h
            try:
                header_db.execute('''INSERT OR REPLACE INTO headers VALUES ('%s', '%s', '%s')''' % (self.header_to_string(last), str(last.get('version')), str(height)))
                header_db_file.commit()
                select = header_db.execute('''SELECT header from headers where algo = '%s' and height < '%s' ORDER BY height DESC LIMIT 10''' % (last.get('version'), str(height))).fetchall()[-1][0]
                first = self.header_from_string(select.decode('hex'))
            except Exception, e:
                print_error('exception: ', e)
            

        if data:
            m = height % 2016
            h_to_insert = data[m*80:(m+1)*80].encode('hex')
            try:
                header_db.execute('''INSERT OR REPLACE INTO headers VALUES ('%s', '%s', '%s')''' % (h_to_insert, str(self.header_from_string(h_to_insert.decode('hex')).get('version')), str(height)))
                header_db_file.commit()
            except Exception, e:
                print_error('exception: ', e)
            if m >= 10:
                raw_header = data[(m-10)*80:(m-9)*80]
                first = self.header_from_string(raw_header)
                raw_l_header = data[m*80:(m+1)*80]
                last = self.header_from_string(raw_l_header)
                try:
                    select = header_db.execute('''SELECT header from headers where algo = '%s' and height < '%s' ORDER BY height DESC LIMIT 10''' % (last.get('version'), height)).fetchall()[-1][0]
                    first = self.header_from_string(select.decode('hex'))
                except Exception, e:
                    
                    print_error('select error: ', e)
            elif height < 10:
                raw_header = data[0:80]
                first = self.header_from_string(raw_header)
                raw_l_header = data[m*80:(m+1)*80]
                last = self.header_from_string(raw_l_header)
            else:
                first = self.read_header(height - 10)
                raw_l_header = data[m*80:(m+1)*80]
                last = self.header_from_string(raw_l_header)
            
        nActualTimespan = last.get('timestamp') - first.get('timestamp')
        nTargetTimespan = 30*5
        nAvgInterval = 10*nTargetTimespan

        numheaders = 10
        #shouldn't need this after a while, assume 10K is enough:
        if height < 10000:
            numheaders = header_db.execute('''SELECT count(*) from headers where algo = '%s' and height < '%s' ''' % (last.get('version'),height)).fetchone()[0]
            print_error('height, numheaders', height, numheaders)

        if numheaders >= 10:
            #seems to be a bug based on what the myriadcoind code says... will check later
            if nActualTimespan < nAvgInterval*(100.0/100.0):
                nActualTimespan = nAvgInterval*(100.0/100.0)
            if nActualTimespan > nAvgInterval*(100.0/100.0):
                nActualTimespan = nAvgInterval*(100.0/100.0)
        else:
            return 0x1e0fffff, 0x00000FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF


        bits = last.get('bits') 
        # convert to bignum
        MM = 256*256*256
        a = bits%MM
        if a < 0x8000:
            a *= 256
        target = (a) * pow(2, 8 * (bits/MM - 3))

        # new target
        new_target = min( max_target, (target * nActualTimespan)/nAvgInterval )
        
        # convert it to bits
        c = ("%064X"%new_target)[2:]
        i = 31
        while c[0:2]=="00":
            c = c[2:]
            i -= 1

        c = int('0x'+c[0:6],16)
        if c >= 0x800000: 
            c /= 256
            i += 1

        new_bits = c + MM * i
        header_db_file.commit()
        header_db_file.close()
        return new_bits, new_target


    def request_header(self, i, h, queue):
        print_error("requesting header %d from %s"%(h, i.server))
        i.send([ ('blockchain.block.get_header',[h])], lambda i,r: queue.put((i,r)))

    def retrieve_header(self, i, queue):
        while True:
            try:
                ir = queue.get(timeout=1)
            except Queue.Empty:
                print_error('timeout')
                continue

            if not ir: 
                continue

            i, r = ir

            if r.get('error'):
                print_error('Verifier received an error:', r)
                continue

            # 3. handle response
            method = r['method']
            params = r['params']
            result = r['result']

            if method == 'blockchain.block.get_header':
                return result
                


    def get_chain(self, interface, final_header):

        header = final_header
        chain = [ final_header ]
        requested_header = False
        queue = Queue.Queue()

        while self.is_running():

            if requested_header:
                header = self.retrieve_header(interface, queue)
                if not header: return
                chain = [ header ] + chain
                requested_header = False

            height = header.get('block_height')
            previous_header = self.read_header(height -1)
            if not previous_header:
                self.request_header(interface, height - 1, queue)
                requested_header = True
                continue

            # verify that it connects to my chain
            prev_hash = self.hash_header(previous_header)
            if prev_hash != header.get('prev_block_hash'):
                print_error("reorg")
                self.request_header(interface, height - 1, queue)
                requested_header = True
                continue

            else:
                # the chain is complete
                return chain


    def get_and_verify_chunks(self, i, header, height):

        queue = Queue.Queue()
        min_index = (self.local_height + 1)/2016
        max_index = (height + 1)/2016
        n = min_index
        while n < max_index + 1:
            print_error( "Requesting chunk:", n )
            r = i.synchronous_get([ ('blockchain.block.get_chunk',[n])])[0]
            if not r: 
                continue
            try:
                self.verify_chunk(n, r)
                n = n + 1
            except Exception:
                print_error('Verify chunk failed!')
                n = n - 1
                if n < 0:
                    return False

        return True

