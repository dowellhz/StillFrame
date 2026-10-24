"""Select a test variant in the generated config; never changes sdkconfig.defaults."""
import sys,pathlib
p=pathlib.Path(__file__).resolve().parents[1]/'sdkconfig'
s=p.read_text().splitlines();keys=['SF_TEST_MODE','SF_TEST_PANIC','SF_RUNTIME_TEST','FATFS_LFN_HEAP','FATFS_LFN_NONE']
s=[l for l in s if not any(l.startswith('CONFIG_'+k+'=') or l=='# CONFIG_'+k+' is not set' for k in keys)]
s+=['CONFIG_FATFS_LFN_HEAP=y']
if sys.argv[1]=='runtime':s+=['CONFIG_SF_RUNTIME_TEST=y']
elif sys.argv[1]=='test':s+=['CONFIG_SF_TEST_MODE=y']
elif sys.argv[1]=='panic':s+=['CONFIG_SF_TEST_PANIC=y']
elif sys.argv[1]!='release':raise SystemExit('variant must be release, panic or test')
p.write_text('\n'.join(s)+'\n')
