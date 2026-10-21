#include "safe_control.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
#ifdef DEMO
    const char *frames[]={"$P,0,0,1,1000,0,X,D2#","$P,0,0,1,1000,0,Y,D2#"};
#else
    const char *frames[]={"$P,0,0,1,1000,0,0,X,2E#","$P,0,0,1,1000,0,0,Y,2E#"};
#endif
    int i,expected,accepted;
    SafeControl s;
    if(argc!=2)return 2;
    expected=atoi(argv[1]);
    for(i=0;i<2;i++){
        safe_init(&s);
        accepted=safe_pframe(&s,frames[i],strlen(frames[i]),12300);
        printf("length=%zu accepted=%d expected=%d\n",strlen(frames[i]),accepted,expected);
        if(accepted!=expected)return 1;
    }
    return 0;
}
