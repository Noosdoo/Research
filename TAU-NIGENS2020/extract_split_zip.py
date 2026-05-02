"""
DCASE split zip (z01+z02 = disk0, zip = central directory) 解凍スクリプト。
メモリに全部読まず、仮想マルチパートファイルでシーク読みする。
"""

import struct, zlib, os, sys

def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def u32(d, o): return struct.unpack_from('<I', d, o)[0]
def u64(d, o): return struct.unpack_from('<Q', d, o)[0]


class MultipartFile:
    """複数ファイルを1つの連続ストリームとして扱う。"""
    def __init__(self, paths):
        self.files  = [open(p, 'rb') for p in paths]
        self.sizes  = [os.path.getsize(p) for p in paths]
        self.starts = []
        cur = 0
        for s in self.sizes:
            self.starts.append(cur)
            cur += s
        self.total = cur
        self._pos  = 0

    def seek(self, offset):
        self._pos = offset

    def read(self, n):
        result = b''
        remaining = n
        pos = self._pos
        while remaining > 0 and pos < self.total:
            # どのファイルか特定
            fi = 0
            for i in range(len(self.starts) - 1, -1, -1):
                if pos >= self.starts[i]:
                    fi = i
                    break
            local_off = pos - self.starts[fi]
            avail = self.sizes[fi] - local_off
            to_read = min(remaining, avail)
            self.files[fi].seek(local_off)
            chunk = self.files[fi].read(to_read)
            result += chunk
            pos += len(chunk)
            remaining -= len(chunk)
        self._pos = pos
        return result

    def close(self):
        for f in self.files:
            f.close()


def parse_extra_zip64(extra, need_uncomp, need_comp, need_offset):
    pos = 0
    while pos + 4 <= len(extra):
        tag  = u16(extra, pos)
        size = u16(extra, pos + 2)
        body = extra[pos+4:pos+4+size]
        if tag == 0x0001:
            bpos = 0
            if need_uncomp is not None and bpos + 8 <= len(body):
                need_uncomp = u64(body, bpos); bpos += 8
            if need_comp  is not None and bpos + 8 <= len(body):
                need_comp   = u64(body, bpos); bpos += 8
            if need_offset is not None and bpos + 8 <= len(body):
                need_offset = u64(body, bpos); bpos += 8
            return need_uncomp, need_comp, need_offset
        pos += 4 + size
    return need_uncomp, need_comp, need_offset


def parse_central_directory(zip_path):
    """foa_dev.zip からセントラルディレクトリを読んでエントリリストを返す。"""
    with open(zip_path, 'rb') as f:
        data = f.read()

    # EOCD を末尾から探す
    eocd_pos = -1
    for i in range(len(data) - 22, max(0, len(data) - 65558), -1):
        if data[i:i+4] == b'PK\x05\x06':
            eocd_pos = i
            break
    if eocd_pos < 0:
        raise RuntimeError("EOCD not found")

    # ZIP64 EOCD を使う
    cd_offset = u32(data, eocd_pos + 16)
    cd_size   = u32(data, eocd_pos + 12)

    loc64 = eocd_pos - 20
    if loc64 >= 0 and data[loc64:loc64+4] == b'PK\x06\x07':
        eocd64_off = u64(data, loc64 + 8)
        if data[eocd64_off:eocd64_off+4] == b'PK\x06\x06':
            cd_size   = u64(data, eocd64_off + 40)
            cd_offset = u64(data, eocd64_off + 48)

    print(f"  CD offset in zip: {cd_offset:#x}, size: {cd_size}")

    entries = []
    pos = cd_offset
    end = cd_offset + cd_size

    while pos < end - 4:
        if data[pos:pos+4] != b'PK\x01\x02':
            break
        flags       = u16(data, pos+8)
        compression = u16(data, pos+10)
        crc         = u32(data, pos+16)
        comp_size   = u32(data, pos+20)
        uncomp_size = u32(data, pos+24)
        name_len    = u16(data, pos+28)
        extra_len   = u16(data, pos+30)
        comment_len = u16(data, pos+32)
        disk_start  = u16(data, pos+34)
        local_off   = u32(data, pos+42)

        name  = data[pos+46:pos+46+name_len].decode('utf-8', errors='replace')
        extra = data[pos+46+name_len:pos+46+name_len+extra_len]

        need_u = uncomp_size if uncomp_size == 0xFFFFFFFF else None
        need_c = comp_size   if comp_size   == 0xFFFFFFFF else None
        need_o = local_off   if local_off   == 0xFFFFFFFF else None
        if need_u is not None or need_c is not None or need_o is not None:
            ru, rc, ro = parse_extra_zip64(extra, need_u, need_c, need_o)
            if need_u is not None: uncomp_size = ru
            if need_c is not None: comp_size   = rc
            if need_o is not None: local_off   = ro

        entries.append({
            'name':        name,
            'compression': compression,
            'crc':         crc,
            'comp_size':   comp_size,
            'uncomp_size': uncomp_size,
            'disk_start':  disk_start,
            'local_off':   local_off,
        })
        pos += 46 + name_len + extra_len + comment_len

    return entries


def extract_entry(mf, disk_offsets, entry, outdir):
    """1エントリを MultipartFile から解凍して保存する。"""
    name = entry['name']
    out_path = os.path.join(outdir, name.replace('/', os.sep))

    if name.endswith('/'):
        os.makedirs(out_path, exist_ok=True)
        return True

    # ディスクオフセットを加算して絶対位置を計算
    disk = entry['disk_start']
    abs_off = disk_offsets[disk] + entry['local_off']

    # ローカルヘッダを読む
    mf.seek(abs_off)
    lhdr = mf.read(30)
    if lhdr[:4] != b'PK\x03\x04':
        print(f"  警告: ローカルヘッダ不正 ({name}) disk={disk} @ abs={abs_off:#x} local={entry['local_off']:#x}")
        return False

    name_len2  = u16(lhdr, 26)
    extra_len2 = u16(lhdr, 28)
    data_start = abs_off + 30 + name_len2 + extra_len2

    mf.seek(data_start)
    compressed = mf.read(entry['comp_size'])

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        if entry['compression'] == 0:
            raw = compressed
        elif entry['compression'] == 8:
            raw = zlib.decompress(bytes(compressed), -15)
        else:
            print(f"  未対応圧縮方式 {entry['compression']}: {name}")
            return False
        with open(out_path, 'wb') as f:
            f.write(raw)
        return True
    except Exception as e:
        print(f"  解凍エラー ({name}): {e}")
        return False


def extract_split_zip(all_parts, zip_path, outdir):
    """
    all_parts: [z01, z02, foa_dev.zip] の順（全ディスクを含む）
    zip_path: セントラルディレクトリ読み出し用（foa_dev.zip）
    """
    print("セントラルディレクトリ解析中...")
    entries = parse_central_directory(zip_path)
    print(f"  エントリ数: {len(entries)}")

    print("データパーツをオープン...")
    mf = MultipartFile(all_parts)
    print(f"  合計データサイズ: {mf.total:,} bytes")

    # 各ディスクの先頭が MultipartFile 内のどのオフセットか
    disk_offsets = list(mf.starts)
    print(f"  disk_offsets: {[f'{o:,}' for o in disk_offsets]}")

    os.makedirs(outdir, exist_ok=True)
    ok = fail = 0
    for i, entry in enumerate(entries):
        if extract_entry(mf, disk_offsets, entry, outdir):
            ok += 1
        else:
            fail += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(entries)} 完了 (成功:{ok} 失敗:{fail})...")

    mf.close()
    print(f"\n解凍完了: 成功 {ok} / 失敗 {fail} / 合計 {len(entries)}")


if __name__ == '__main__':
    base = r'C:\Users\satos\research\TAU-NIGENS2020'
    # disk0=z01, disk1=z02, disk2=foa_dev.zip（音声データ+CD）
    all_parts = [
        os.path.join(base, 'foa_dev.z01'),
        os.path.join(base, 'foa_dev.z02'),
        os.path.join(base, 'foa_dev.zip'),
    ]
    zip_path = os.path.join(base, 'foa_dev.zip')
    outdir   = os.path.join(base, 'foa_dev')
    extract_split_zip(all_parts, zip_path, outdir)
