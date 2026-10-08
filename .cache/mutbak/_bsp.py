import numpy as np, torch, sys
sys.path.insert(0,'.cache/xcheck')
import probe_hinge_layers as P, causal_inject as CI
from transformers import AutoTokenizer, AutoModelForCausalLM
NPZ='datasets/aime_qwen3_1p7b_16k_fp16/aime'
pos=P.load_positives(); tmap={t:P.real_T(t) for t in pos}
W,_=CI.train_direction(pos,tmap,CI.SEED); gap=CI.class_gap(pos,tmap,CI.SEED)
tk=AutoTokenizer.from_pretrained(CI.MODEL); mid,cid=CI.load_marker_ids(tk); mt=torch.as_tensor(mid)
model=AutoModelForCausalLM.from_pretrained(CI.MODEL,dtype=torch.float32); model.eval()
blk=model.model.layers[20]
c=CI.build_cases(pos,tmap)[0]
z=np.load('%s/%s.npz'%(NPZ,c['traj']))
full=np.concatenate([z['prompt_token_ids'].astype(np.int64), z['token_ids'].astype(np.int64)])
inj=len(z['prompt_token_ids'])+c['t']-1
pre=torch.as_tensor(full[:inj+1])[None,:]
Z=np.zeros_like(W)
vs=[Z, 0.5*W, 1.0*W, 2.0*W, 4.0*W, -0.5*W]          # 与 causal_inject 交叉校验同一组

def idx_batch(V):
    B=len(V)
    delta=torch.as_tensor(np.stack(V),dtype=torch.float32)
    pi=torch.full((B,),inj,dtype=torch.long); bi=torch.arange(B)
    def h(m,inp):
        x=inp[0].clone(); x[bi,pi,:]=x[bi,pi,:]+delta; return (x,)+inp[1:]
    hd=blk.register_forward_pre_hook(h)
    try:
        with torch.no_grad(): lg=model(pre.expand(B,pre.shape[1])).logits[:,-1,:]
    finally: hd.remove()
    lp=torch.log_softmax(lg,dim=-1)
    return np.array([float(torch.logsumexp(lp[b][mt],dim=0)) for b in range(B)])

def cat_one(v):
    vv=torch.as_tensor(v,dtype=torch.float32)
    def h(m,inp):
        return (torch.cat([inp[0][:,:inj,:], inp[0][:,inj:inj+1,:]+vv, inp[0][:,inj+1:,:]],dim=1),)+inp[1:]
    hd=blk.register_forward_pre_hook(h)
    try:
        with torch.no_grad(): lg=model(pre).logits[0,-1]
    finally: hd.remove()
    return float(torch.logsumexp(torch.log_softmax(lg,dim=-1)[mt],dim=0))

res={}
res['B1_idx']=np.array([idx_batch([v])[0] for v in vs])
res['B6_idx']=idx_batch(vs)
res['B29_idx']=idx_batch(vs+[Z]*23)[:6]
res['B1_cat']=np.array([cat_one(v) for v in vs])
ks=list(res)
print('  L=%d  %s t=%d'%(pre.shape[1], c['traj'][:30], c['t']), flush=True)
for i in range(len(ks)):
    for j in range(i+1,len(ks)):
        print('  %-9s vs %-9s  最大差 %.3e'%(ks[i],ks[j],float(np.abs(res[ks[i]]-res[ks[j]]).max())), flush=True)
