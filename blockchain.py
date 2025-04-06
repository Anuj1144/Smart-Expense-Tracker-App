import hashlib
import json
import time

class Blockchain:
    def __init__(self):
        self.chain = []
        self.create_block(proof=1, previous_hash='0')

    def create_block(self, proof, previous_hash):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time.time(),
            'proof': proof,
            'previous_hash': previous_hash,
            'transactions': []
        }
        self.chain.append(block)
        return block

    def get_previous_block(self):
        return self.chain[-1]

    def add_transaction(self, transaction):
        self.get_previous_block()['transactions'].append(transaction)
        block = self.create_block(proof=1, previous_hash=self.hash(self.get_previous_block()))
        return self.hash(block)

    def hash(self, block):
        encoded_block = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(encoded_block).hexdigest()

if __name__ == "__main__":
    bc = Blockchain()
    print(bc.add_transaction("Test Transaction"))