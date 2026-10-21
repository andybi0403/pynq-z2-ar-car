import json
import urllib.request

allowed={'ssid','channel','band','up','enabled','disabled','status','country','hwmode','htmode','hidden','code','msg','ifname','device'}
def public_only(value):
    if isinstance(value,list):return [public_only(item) for item in value]
    if isinstance(value,dict):
        return {key:public_only(item) for key,item in value.items()
                if key in allowed or isinstance(item,(dict,list))}
    return value
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
result={'kind':'ROUTER_RADIO_READ_ONLY','network_changed':False}
for path in ('/cgi-bin/api/router/nologin/apinfo','/cgi-bin/api/wireless/get'):
    try:
        with opener.open('http://192.168.8.1'+path,timeout=3) as response:
            result[path]=public_only(json.loads(response.read(300000)))
    except Exception as exc:result[path]={'error':type(exc).__name__}
print(json.dumps(result))
