import unittest
import struct
import hashlib
from unittest.mock import patch
from wlre.services.world.itemdata_v1 import parse_itemdata, ItemDataDecodeError


def sample(iid=39852, price=125, name='蘋果'):
    enc=lambda s: s.encode('utf-16-le')
    namebytes=enc(name);kindbytes=enc('雜物')
    out=struct.pack('<H',len(namebytes))+namebytes+b'\x01'+struct.pack('<H',len(kindbytes))+kindbytes
    out+=struct.pack('<H',iid)
    out+=bytes(2+2+2+4*2+2*(2+1+4)+4+4*4*4)
    out+=struct.pack('<BBIIBH',0,10,price,55,2,16)
    out+=bytes(4+1+4+2+5*2)
    out+=struct.pack('<H',0)
    out+=bytes(3+2+1+1)
    out+=bytes(1+2+2+2+2+1+1+1)
    out+=bytes(1+1+1+2+2+2+2+2)
    out+=bytes(6*4)
    out+=bytes(2+2+1+1+1+1+1+1+2+1)
    out+=bytes(5*2)
    out+=bytes(1+2+2+2)
    return out


class ItemDataTests(unittest.TestCase):
    def test_itemdata_price_and_sale_restrictions(self):
        result=parse_itemdata(struct.pack('<I',1)+sample())
        self.assertEqual(result[39852]['name'],'蘋果')
        self.assertEqual(result[39852]['price'],125)
        self.assertEqual(result[39852]['sell_price'],55)
        self.assertEqual(result[39852]['restrict'],16)
        self.assertEqual(result[39852]['open_used'],0)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ItemDataDecodeError):
            parse_itemdata(struct.pack('<I',2)+sample()+sample())

    def test_truncated_and_extra_payload_rejected(self):
        blob=struct.pack('<I',1)+sample()
        for raw in (blob[:-1],blob+b'\x00'):
            with self.assertRaises(ItemDataDecodeError):
                parse_itemdata(raw)

    def test_invalid_unicode_rejected(self):
        blob=bytearray(struct.pack('<I',1)+sample())
        blob[4]=3
        with self.assertRaises(ItemDataDecodeError):
            parse_itemdata(bytes(blob))



    def test_reviewed_1296_extended_fields_and_legacy_isolation(self):
        # Independent synthetic wire values for official ItemData:New fields.
        blob=bytearray(sample(321,name='A'))
        # u16 name bytes + UTF16 A + kind + u16 kind bytes + kind + item ID.
        start=2+2+1+2+len('雜物'.encode('utf-16-le'))+2
        struct.pack_into('<HHH',blob,start,7,4321,5432)
        struct.pack_into('<HBiHBi',blob,start+6+8,25,2,-17,26,3,450)
        material_at=start+6+8+14
        struct.pack_into('<BBBB',blob,material_at,3,44,5,67)
        spares_at=material_at+4+64+13+11
        struct.pack_into('<5H',blob,spares_at,8,9,10,11,12)
        size_at=spares_at+10+2
        struct.pack_into('<3B',blob,size_at,2,3,4)
        struct.pack_into('<2B',blob,size_at+5,6,7)
        time_at=size_at+7+12+3
        struct.pack_into('<3H',blob,time_at,13,14,15)
        blob[time_at+6+4+24+5]=1
        legacy=struct.pack('<I',1)+blob
        self.assertNotIn('icon_id',parse_itemdata(legacy)[321])
        raw=legacy+struct.pack('<H',6789)
        with patch('wlre.services.world.itemdata_v1.ITEMDATA_1296_SHA256',hashlib.sha256(raw).hexdigest()):
            row=parse_itemdata(raw,package_version='1296_2026_11_04_13_34_19_13')[321]
        self.assertEqual(row['attributes'],[{'kind':25,'effect':2,'value':-17},{'kind':26,'effect':3,'value':450}])
        self.assertEqual(row['flags2'],1);self.assertTrue(row['is_pvp_time_over']);self.assertFalse(row['stackable'])
        expected={'kind':1,'order':7,'icon_id':4321,'shop_icon_id':5432,
                  'material':3,'level':44,'fit_type':5,'special':67,
                  'spares':[8,9,10,11,12],'size_l':2,'size_w':3,'size_h':4,
                  'item_w':6,'item_h':7,'available_time':13,'limited_time':14,
                  'use_count':15,'style_bank_set_sort_id':6789}
        self.assertEqual({key:row[key] for key in expected},expected)

if __name__=='__main__':unittest.main()
