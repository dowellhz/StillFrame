"""Exercise the real SDK DHCP parser with exact-size buffers under ASan/UBSan.
Only platform structs/constants are stubbed; parser code is extracted verbatim.
"""
from pathlib import Path
import argparse,subprocess,tempfile,re
root=Path(__file__).resolve().parents[2];p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=root/'.tools/esp-idf/components/lwip/apps/dhcpserver/dhcpserver.c');a=p.parse_args();source=a.source.read_text();start=source.index('static u8_t parse_options(');end=source.index('/******************************************************************************',start);parser=source[start:end]
names=['DHCPDISCOVER','DHCPREQUEST','DHCPDECLINE','DHCPRELEASE','DHCP_OPTION_MSG_TYPE','DHCP_OPTION_REQ_IPADDR','DHCP_OPTION_END','DHCP_OPTION_PAD','DHCPS_STATE_OFFER','DHCPS_STATE_DECLINE','DHCPS_STATE_ACK','DHCPS_STATE_NAK','DHCPS_STATE_IDLE','DHCPS_STATE_RELEASE'];defs=[]
for name in names:
 m=re.search(r'^#define\s+'+name+r'\s+(\d+)',source,re.M)
 if m:defs.append('#define '+name+' '+m[1])
header='''#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint8_t u8_t;typedef uint16_t u16_t;typedef int16_t s16_t;
typedef struct {uint32_t addr;} ip4_addr_t;
typedef struct {uint32_t client_address;bool renew;} dhcps_t;
struct dhcps_state {u8_t state;};
#define DHCPS_DEBUG 0
'''
main='''int main(void){dhcps_t s={0};u8_t short_option[]={53};assert(parse_options(&s,short_option,sizeof(short_option))==DHCPS_STATE_IDLE);
u8_t padded[]={0,0,53,1,1,255};assert(parse_options(&s,padded,sizeof(padded))==DHCPS_STATE_OFFER);
u8_t empty_type[]={53,0,255};assert(parse_options(&s,empty_type,sizeof(empty_type))==DHCPS_STATE_IDLE);
u8_t short_ip[]={50,3,1,2,3,255};assert(parse_options(&s,short_ip,sizeof(short_ip))==DHCPS_STATE_IDLE);
uint32_t rng=0x53ab16;
for(int i=0;i<50000;i++){rng=rng*1664525u+1013904223u;size_t n=rng%512;u8_t *b=malloc(n?n:1);assert(b);for(size_t j=0;j<n;j++){rng=rng*1664525u+1013904223u;b[j]=rng>>24;}s.renew=i&1;parse_options(&s,b,n);free(b);}
puts("PASS: actual SDK DHCP parser, 50000 malformed/random option buffers, ASan + UBSan");return 0;}
'''
with tempfile.TemporaryDirectory(prefix='stillframe-dhcp-') as d:
 d=Path(d);c=d/'parser.c';exe=d/'parser';c.write_text(header+'\n'.join(defs)+'\n'+parser+'\n'+main)
 subprocess.run(['clang','-std=c11','-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(c),'-o',str(exe)],check=True)
 raise SystemExit(subprocess.run([str(exe)]).returncode)
