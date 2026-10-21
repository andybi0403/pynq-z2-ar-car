"""Read every bound input, hash it and syntax-check every Python source without importing it."""
import argparse,collections,hashlib,json
from pathlib import Path
from source_provenance import ROOT,current_identity


def inventory():
    identity=current_identity();files=[];groups=collections.Counter()
    for name,digest in identity['sources'].items():
        path=ROOT.parent/name[len('workspace/'):] if name.startswith('workspace/') else ROOT/name
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=digest:raise RuntimeError('source changed while reading: '+name)
        try:text=content.decode('utf-8-sig');encoding='utf-8'
        except UnicodeDecodeError:text=content.decode('gb18030',errors='replace');encoding='legacy-text'
        if path.suffix=='.py':compile(text,str(path),'exec')
        group=('dependency' if name.startswith('third_party/') else 'STM32_PC' if name.startswith('workspace/') else
               'RTL' if '/rtl/' in name else 'test' if '/tests/' in name or '/tb/' in name else 'PS_build_contract')
        groups[group]+=1;files.append(dict(path=name,sha256=digest,bytes=len(content),lines=len(text.splitlines()),group=group,encoding=encoding))
    return {'schema':'car-source-read-inventory/v1','files':files,'groups':dict(groups),
            'total_files':len(files),'total_lines':sum(f['lines'] for f in files),
            'scope':'all provenance-bound production, tests, build, firmware/PC and pinned IP text; generated outputs excluded',
            'semantic_review':'five-round reports cover critical behavior; Python syntax is checked without hardware imports',
            'hardware_acceptance':'PENDING'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=inventory();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ALL_SOURCE_READ_PASS',result['total_files'],'files',result['total_lines'],'lines',result['groups'])
