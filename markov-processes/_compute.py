"""Every number that appears in a figure of markov-processes/. Pure stdlib."""
import json, math, random
R = {}
def mul(A,B): return [[sum(A[i][k]*B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]
def r4(M,d=4): return [[round(x,d) for x in row] for row in M]

# 1 — three-state service chain -------------------------------------------------
P = [[0.90,0.08,0.02],[0.40,0.50,0.10],[0.30,0.20,0.50]]
pw = {1:P}
M = P
for n in range(2,65):
    M = mul(M,P)
    if n in (2,4,8,16,32,64): pw[n] = M
pi = pw[64][0]
R['powers'] = {'P':P, 'rows':{n:r4(pw[n]) for n in (1,2,4,8,16)}, 'pi':[round(x,5) for x in pi],
               'check_piP':[round(x,5) for x in mul([pi],P)[0]]}
# how many steps until every row is within 0.001 of pi (TV)
M = [[1,0,0],[0,1,0],[0,0,1]]; steps=None
for n in range(1,200):
    M = mul(M,P)
    tv = max(0.5*sum(abs(M[i][j]-pi[j]) for j in range(3)) for i in range(3))
    if tv < 1e-3: steps=n; break
R['powers']['steps_to_1e-3'] = steps

# 2 — two-state chains, exact second eigenvalue ---------------------------------
def two(p,q,n):  # p = P(0->1), q = P(1->0); lambda2 = 1-p-q
    lam = 1-p-q
    piv = [q/(p+q), p/(p+q)]
    # TV from start state 0 after n steps = pi_1 * |lam|^n
    return lam, piv, [round(piv[1]*abs(lam)**k,5) for k in range(n)]
R['spectral'] = {}
for name,(p,q) in {'fast':(0.5,0.5),'medium':(0.1,0.1),'slow':(0.02,0.02)}.items():
    lam,piv,tv = two(p,q,41)
    tmix = next(k for k,v in enumerate(tv) if v <= 0.25)
    R['spectral'][name] = {'p':p,'q':q,'lambda2':round(lam,4),'pi':[round(x,3) for x in piv],
                           'tv':tv,'t_mix_quarter':tmix,
                           'bound':round(math.log(4*1)/ (1-abs(lam)),1) if abs(lam)<1 else None}

# 3 — absorbing retry ladder ----------------------------------------------------
# attempts 1..4; each attempt: succeed .70, retry .25, hard-fail .05; after 4th retry -> fail
s_,r_,f_ = 0.70,0.25,0.05
k = 4
Q = [[0.0]*k for _ in range(k)]
for i in range(k-1): Q[i][i+1] = r_
Rm = [[s_, f_] for i in range(k)]
Rm[k-1] = [s_, f_+r_]
def inv(A):
    n=len(A); Aug=[row[:]+[1.0 if i==j else 0.0 for j in range(n)] for i,row in enumerate(A)]
    for c in range(n):
        p=max(range(c,n),key=lambda r:abs(Aug[r][c])); Aug[c],Aug[p]=Aug[p],Aug[c]
        d=Aug[c][c]; Aug[c]=[x/d for x in Aug[c]]
        for r in range(n):
            if r!=c and Aug[r][c]:
                f=Aug[r][c]; Aug[r]=[a-f*b for a,b in zip(Aug[r],Aug[c])]
    return [row[n:] for row in Aug]
I_Q = [[(1.0 if i==j else 0.0)-Q[i][j] for j in range(k)] for i in range(k)]
N = inv(I_Q)
B = mul(N,Rm)
R['absorbing'] = {'s':s_,'r':r_,'f':f_,'attempts':k,'N':r4(N,4),
                  'expected_attempts':round(sum(N[0]),4),
                  'p_success':round(B[0][0],4),'p_fail':round(B[0][1],4),
                  'variance_note':'row 0 of N gives visits to each attempt state'}

# 4 — PageRank on an 8-node graph with a dangling node ---------------------------
links = {'A':['B','C'],'B':['C'],'C':['A'],'D':['A','C'],'E':['D','F'],'F':['E','G'],'G':['C'],'H':[]}
nodes = sorted(links); n = len(nodes); idx = {v:i for i,v in enumerate(nodes)}
d = 0.85
def pagerank(damp, iters=200):
    x = [1.0/n]*n
    for _ in range(iters):
        y = [0.0]*n
        dangling = sum(x[idx[v]] for v in nodes if not links[v])
        for v in nodes:
            out = links[v]
            if out:
                share = x[idx[v]]/len(out)
                for w in out: y[idx[w]] += share
        y = [damp*(yi + dangling/n) + (1-damp)/n for yi in y]
        s = sum(y); y=[v/s for v in y]
        if max(abs(a-b) for a,b in zip(x,y)) < 1e-12: x=y; break
        x = y
    return x
pr = pagerank(d)
# iterations to 1e-6 L1
def iters_to(tol, damp):
    x=[1.0/n]*n
    for it in range(1,500):
        y=[0.0]*n; dangling=sum(x[idx[v]] for v in nodes if not links[v])
        for v in nodes:
            out=links[v]
            if out:
                sh=x[idx[v]]/len(out)
                for w in out: y[idx[w]]+=sh
        y=[damp*(yi+dangling/n)+(1-damp)/n for yi in y]
        s=sum(y); y=[v/s for v in y]
        if sum(abs(a-b) for a,b in zip(x,y))<tol: return it
        x=y
R['pagerank'] = {'links':links,'d':d,'ranks':{v:round(pr[idx[v]],4) for v in nodes},
                 'order':sorted(nodes,key=lambda v:-pr[idx[v]]),
                 'iters_1e-6':{'0.85':iters_to(1e-6,0.85),'0.99':iters_to(1e-6,0.99),'0.50':iters_to(1e-6,0.50)},
                 'ranks_d99':{v:round(pagerank(0.99)[idx[v]],4) for v in nodes}}

# 5 — Metropolis-Hastings on a standard normal ----------------------------------
def mh(sigma, N=200000, seed=7):
    rng = random.Random(seed); x=0.0; acc=0; xs=[]
    logp = lambda z: -0.5*z*z
    for _ in range(N):
        y = x + rng.gauss(0,sigma)
        if math.log(rng.random()) < logp(y)-logp(x): x=y; acc+=1
        xs.append(x)
    m = sum(xs)/N; v = sum((z-m)**2 for z in xs)/N
    # lag-1..50 autocorrelation -> integrated autocorr time
    ac=[]; 
    for lag in range(1,60):
        c = sum((xs[i]-m)*(xs[i+lag]-m) for i in range(0,N-lag,7))/ (len(range(0,N-lag,7)))
        ac.append(c/v)
    tau = 1+2*sum(a for a in ac if a>0.01)
    return {'sigma':sigma,'accept':round(acc/N,3),'mean':round(m,3),'sd':round(math.sqrt(v),3),
            'tau_int':round(tau,1),'ess_per_1000':round(1000/tau,1)}
R['mh'] = [mh(s) for s in (0.1,0.5,2.4,10.0)]

# 6 — HMM + Viterbi: Human vs Bot traffic ---------------------------------------
states=['Human','Bot']; start={'Human':0.8,'Bot':0.2}
trans={'Human':{'Human':0.9,'Bot':0.1},'Bot':{'Human':0.2,'Bot':0.8}}
emit={'Human':{'page':0.5,'asset':0.4,'api':0.1},'Bot':{'page':0.2,'asset':0.1,'api':0.7}}
obs=['page','api','api','asset']
V=[{}]; path={}
for s in states: V[0][s]=math.log(start[s]*emit[s][obs[0]]); path[s]=[s]
tr=[{s:{'from':None,'val':V[0][s]} for s in states}]
for t in range(1,len(obs)):
    V.append({}); newpath={}; lay={}
    for s in states:
        best=max(((V[t-1][p]+math.log(trans[p][s])+math.log(emit[s][obs[t]]),p) for p in states))
        V[t][s]=best[0]; newpath[s]=path[best[1]]+[s]; lay[s]={'from':best[1],'val':best[0]}
    path=newpath; tr.append(lay)
best=max((V[-1][s],s) for s in states)
# forward probability of the observation sequence
f=[{s:start[s]*emit[s][obs[0]] for s in states}]
for t in range(1,len(obs)):
    f.append({s:sum(f[t-1][p]*trans[p][s] for p in states)*emit[s][obs[t]] for s in states})
R['viterbi']={'obs':obs,'start':start,'trans':trans,'emit':emit,
  'trellis':[{s:{'from':lay[s]['from'],'log':round(lay[s]['val'],3),'p':round(math.exp(lay[s]['val']),6)} for s in states} for lay in tr],
  'best_path':path[best[1]],'best_log':round(best[0],3),'best_p':round(math.exp(best[0]),6),
  'forward_p':round(sum(f[-1].values()),6),
  'posterior_of_best':round(math.exp(best[0])/sum(f[-1].values()),4)}

# 7 — value iteration on a 6-cell corridor --------------------------------------
Ns=6; gamma=0.9; slip=0.1; step_cost=-0.02
def vi():
    V=[0.0]*Ns; hist=[V[:]]
    for sweep in range(60):
        nv=V[:]
        for s in range(Ns-1):
            best=-9e9
            for a,(intended,other) in {'right':(min(s+1,Ns-1),max(s-1,0)),'left':(max(s-1,0),min(s+1,Ns-1))}.items():
                q=(1-slip)*( (1.0 if intended==Ns-1 else 0.0)+gamma*V[intended]) + slip*((1.0 if other==Ns-1 else 0.0)+gamma*V[other]) + step_cost
                best=max(best,q)
            nv[s]=best
        d=max(abs(a-b) for a,b in zip(nv,V)); V=nv; hist.append(V[:])
        if d<1e-9: break
    return V,hist
V,hist=vi()
R['value_iteration']={'gamma':gamma,'slip':slip,'step_cost':step_cost,'goal_reward':1.0,
  'sweeps':[ [round(x,3) for x in hist[i]] for i in (0,1,2,3,5,10)],
  'final':[round(x,4) for x in V],'n_sweeps':len(hist)-1,
  'contraction':'||V_{k+1}-V*||<=gamma^k||V_0-V*||, gamma=0.9 -> 1e-3 in %d sweeps'%math.ceil(math.log(1e-3)/math.log(0.9))}

# 8 — Smith 2-bit saturating counter --------------------------------------------
def two_bit(p):
    # states 0=SN 1=WN 2=WT 3=ST ; predict taken in 2,3 ; taken w.p. p
    T=[[1-p,p,0,0],[1-p,0,p,0],[0,1-p,0,p],[0,0,1-p,p]]
    x=[0.25]*4
    for _ in range(20000):
        x=[sum(x[i]*T[i][j] for i in range(4)) for j in range(4)]
    mis = (x[0]+x[1])*p + (x[2]+x[3])*(1-p)
    return {'p':p,'pi':[round(v,4) for v in x],'mispredict':round(mis,4),'one_bit':round(2*p*(1-p),4)}
R['two_bit']=[two_bit(p) for p in (0.5,0.6,0.7,0.8,0.9,0.95)]
R['two_bit_matrix']=[[round(v,2) for v in row] for row in [[1-0.9,0.9,0,0],[1-0.9,0,0.9,0],[0,1-0.9,0,0.9],[0,0,1-0.9,0.9]]]

# 9 — M/M/1 -----------------------------------------------------------------------
R['mm1']=[{'rho':rho,'L':round(rho/(1-rho),2),'Lq':round(rho*rho/(1-rho),2),
           'W_over_S':round(1/(1-rho),2),'Wq_over_S':round(rho/(1-rho),2),
           'p_gt_10':round(rho**11,5)} for rho in (0.5,0.7,0.8,0.9,0.95,0.99)]
# M/M/c Erlang-C for c servers, offered load a=lambda/mu
def erlang_c(c,a):
    s=sum(a**k/math.factorial(k) for k in range(c))
    top=a**c/(math.factorial(c)*(1-a/c))
    return top/(s+top)
R['erlang']=[{'c':c,'a':round(0.8*c,1),'rho':0.8,'P_wait':round(erlang_c(c,0.8*c),4),
              'Wq_over_S':round(erlang_c(c,0.8*c)/(c*(1-0.8)),4)} for c in (1,2,4,8,16,32)]

# 10 — availability CTMC ----------------------------------------------------------
def avail(mttf,mttr):
    A=mttf/(mttf+mttr); down=(1-A)*365.25*24*60
    return {'mttf_h':mttf,'mttr_h':mttr,'A':round(A,7),'nines':round(-math.log10(1-A),2),
            'downtime_min_per_year':round(down,1)}
R['availability']=[avail(720,1),avail(720,0.083),avail(8760,4),avail(2190,0.5)]
R['availability_2of2']=round(1-(1-720/721)**2,7)

# 11 — state sizes ---------------------------------------------------------------
def kv(layers,kv_heads,head_dim,bytes_per=2):
    per_tok = 2*layers*kv_heads*head_dim*bytes_per
    return {'layers':layers,'kv_heads':kv_heads,'head_dim':head_dim,'bytes_per_token':per_tok,
            'KiB_per_token':round(per_tok/1024,1),
            'GiB_at_128k':round(per_tok*131072/1024**3,2),
            'GiB_at_1M':round(per_tok*1048576/1024**3,2)}
R['kv']={'gqa_70b':kv(80,8,128),'mha_70b':kv(80,64,128)}
R['ssm_state']={'layers':64,'d_inner':8192,'d_state':16,'bytes_per':2,
                'bytes_total':64*8192*16*2,'MiB':round(64*8192*16*2/1024**2,1)}
R['ngram_state']={'order':5,'tokens_carried':4,'bytes':4*4}

# 12 — exponential vs Pareto tails ------------------------------------------------
mean=100.0
alpha=1.5; xm=mean*(alpha-1)/alpha
def tails(x):
    return {'x_ms':x,'exp':float('%.3g'%math.exp(-x/mean)),
            'pareto':float('%.3g'%((xm/x)**alpha if x>xm else 1.0))}
R['tails']={'mean_ms':mean,'alpha':alpha,'x_m':round(xm,2),
            'points':[tails(x) for x in (200,500,1000,10000,100000)],
            'p99_exp':round(-mean*math.log(0.01),1),
            'p99_pareto':round(xm/(0.01**(1/alpha)),1),
            'p999_exp':round(-mean*math.log(0.001),1),
            'p999_pareto':round(xm/(0.001**(1/alpha)),1)}
print(json.dumps(R,indent=1,default=str))
