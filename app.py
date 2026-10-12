"""Mutual Ledger: private pilot application. Run: uvicorn app:app --reload"""
import os, sqlite3, secrets, hashlib, hmac, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal

ROOT=Path(__file__).parent
DB=Path(os.environ.get('LEDGER_DB', ROOT/'ledger.db'))
DB.parent.mkdir(parents=True, exist_ok=True)
app=FastAPI(title='Mutual Ledger', version='0.1.0')

def now():return datetime.now(timezone.utc).isoformat()
@contextmanager
def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
 try:yield c;c.commit()
 except: c.rollback();raise
 finally:c.close()
def init():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,password_hash TEXT NOT NULL,company TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id));
  CREATE TABLE IF NOT EXISTS ledgers(id INTEGER PRIMARY KEY,title TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('supplier','accountant')),currency TEXT NOT NULL,creator_id INTEGER NOT NULL REFERENCES users(id), counterparty_id INTEGER REFERENCES users(id), invite_token TEXT UNIQUE,invite_email TEXT NOT NULL, opening_minor INTEGER NOT NULL,opening_creator_ok INTEGER NOT NULL DEFAULT 1,opening_other_ok INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY,ledger_id INTEGER NOT NULL REFERENCES ledgers(id),kind TEXT NOT NULL CHECK(kind IN ('credit','debit','invoice')), description TEXT NOT NULL,amount_minor INTEGER NOT NULL CHECK(amount_minor>0), created_by INTEGER NOT NULL REFERENCES users(id),creator_ok INTEGER NOT NULL DEFAULT 1,other_ok INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS invoice_lines(id INTEGER PRIMARY KEY,transaction_id INTEGER NOT NULL REFERENCES transactions(id),description TEXT NOT NULL,qty INTEGER NOT NULL CHECK(qty>0),amount_minor INTEGER NOT NULL CHECK(amount_minor>0));
  CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY,line_id INTEGER NOT NULL REFERENCES invoice_lines(id),qty INTEGER NOT NULL CHECK(qty>0),created_by INTEGER NOT NULL REFERENCES users(id),creator_ok INTEGER NOT NULL DEFAULT 1,other_ok INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ledger_id INTEGER NOT NULL,actor_id INTEGER NOT NULL,verb TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
  ''')
  columns=[r[1] for r in c.execute('PRAGMA table_info(sessions)')]
  if 'expires_at' not in columns:c.execute('ALTER TABLE sessions ADD COLUMN expires_at TEXT')
init()

def hash_pw(p):
 salt=os.urandom(16);return salt.hex()+':'+hashlib.scrypt(p.encode(),salt=salt,n=16384,r=8,p=1).hex()
def verify_pw(p,stored):
 try:
  salt,val=stored.split(':');return hmac.compare_digest(hashlib.scrypt(p.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex(),val)
 except Exception:return False
class Register(BaseModel):
 email:str;name:str;company:str;password:str=Field(min_length=10)
class Login(BaseModel):email:str;password:str
class LedgerCreate(BaseModel):
 title:str=Field(min_length=2);kind:Literal['supplier','accountant'];currency:str=Field(pattern='^[A-Z]{3}$');invite_email:str;opening_minor:int
class Entry(BaseModel):kind:Literal['credit','debit'];description:str=Field(min_length=2);amount_minor:int=Field(gt=0)
class Line(BaseModel):description:str=Field(min_length=2);qty:int=Field(gt=0);amount_minor:int=Field(gt=0)
class Invoice(BaseModel):description:str=Field(min_length=2);lines:list[Line]=Field(min_length=1)
class Delivery(BaseModel):qty:int=Field(gt=0)
def user(authorization:str|None=Header(None)):
 token=(authorization or '').removeprefix('Bearer ').strip()
 with db() as c:
  u=c.execute('SELECT u.id,u.email,u.name,u.company FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND (s.expires_at IS NULL OR s.expires_at>?)',(token,now())).fetchone()
 if not u:raise HTTPException(401,'Please sign in')
 return dict(u)
def ledger(c,lid,uid,joined=True):
 l=c.execute('SELECT * FROM ledgers WHERE id=?',(lid,)).fetchone()
 if not l or uid not in [l['creator_id'],l['counterparty_id']]:raise HTTPException(404,'Ledger not found')
 if joined and not l['counterparty_id']:raise HTTPException(409,'Waiting for the invited counterparty to join')
 return l
def who(l,uid):return 'creator' if l['creator_id']==uid else 'other'
def audit(c,lid,uid,verb,details):c.execute('INSERT INTO audit(ledger_id,actor_id,verb,details,created_at) VALUES (?,?,?,?,?)',(lid,uid,verb,json.dumps(details),now()))
@app.middleware('http')
async def secure_headers(request:Request, call_next):
 response=await call_next(request)
 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['Referrer-Policy']='no-referrer'
 response.headers['X-Frame-Options']='DENY'
 response.headers['Cache-Control']='no-store'
 response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
 return response
@app.get('/healthz')
def healthz():return {'status':'ok'}
@app.get('/')
def home():return FileResponse(ROOT/'static'/'index.html')
@app.post('/api/register')
def register(x:Register):
 with db() as c:
  try:
   c.execute('INSERT INTO users(email,name,password_hash,company) VALUES (?,?,?,?)',(x.email.lower().strip(),x.name.strip(),hash_pw(x.password),x.company.strip()))
  except sqlite3.IntegrityError:raise HTTPException(409,'Email already registered')
 return {'ok':True}
@app.post('/api/login')
def login(x:Login):
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(x.email.lower().strip(),)).fetchone()
  if not u or not verify_pw(x.password,u['password_hash']):raise HTTPException(401,'Incorrect email or password')
  token=secrets.token_urlsafe(40);c.execute('INSERT INTO sessions(token,user_id,expires_at) VALUES (?,?,?)',(token,u['id'],(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()))
 return {'token':token,'user':{'id':u['id'],'name':u['name'],'company':u['company'],'email':u['email']}}
@app.post('/api/logout')
def logout(u=Depends(user),authorization:str|None=Header(None)):
 with db() as c:c.execute('DELETE FROM sessions WHERE token=?',((authorization or '').removeprefix('Bearer ').strip(),))
 return {'ok':True}
@app.get('/api/me')
def me(u=Depends(user)):return u
@app.get('/api/ledgers')
def ledgers(u=Depends(user)):
 with db() as c:
  data=c.execute('SELECT l.*,a.company AS counterparty_company FROM ledgers l LEFT JOIN users a ON a.id=CASE WHEN l.creator_id=? THEN l.counterparty_id ELSE l.creator_id END WHERE l.creator_id=? OR l.counterparty_id=? ORDER BY l.id DESC',(u['id'],u['id'],u['id'])).fetchall()
 return [dict(r) for r in data]
@app.post('/api/ledgers')
def create_ledger(x:LedgerCreate,u=Depends(user)):
 if x.invite_email.strip().lower()==u['email']:raise HTTPException(400,'Invite a different email')
 with db() as c:
  token=secrets.token_urlsafe(24)
  cur=c.execute('INSERT INTO ledgers(title,kind,currency,creator_id,invite_token,invite_email,opening_minor,created_at) VALUES (?,?,?,?,?,?,?,?)',(x.title,x.kind,x.currency,u['id'],token,x.invite_email.lower().strip(),x.opening_minor,now()))
  lid=cur.lastrowid;audit(c,lid,u['id'],'ledger.created',{'kind':x.kind,'opening_minor':x.opening_minor})
 return {'id':lid,'invite_token':token,'invite_path':'/?invite='+token}
@app.post('/api/invite/{token}/accept')
def accept(token:str,u=Depends(user)):
 with db() as c:
  l=c.execute('SELECT * FROM ledgers WHERE invite_token=?',(token,)).fetchone()
  if not l:raise HTTPException(404,'Invitation not found')
  if l['counterparty_id']:raise HTTPException(409,'Invitation already accepted')
  if u['email']!=l['invite_email']:raise HTTPException(403,'Sign in using the invited email address')
  c.execute('UPDATE ledgers SET counterparty_id=?,invite_token=NULL WHERE id=?',(u['id'],l['id']))
  audit(c,l['id'],u['id'],'invite.accepted',{})
 return {'ledger_id':l['id']}
@app.get('/api/ledgers/{lid}')
def detail(lid:int,u=Depends(user)):
 with db() as c:
  l=ledger(c,lid,u['id'],False)
  transactions=[dict(x) for x in c.execute('SELECT * FROM transactions WHERE ledger_id=? ORDER BY id DESC',(lid,))]
  for t in transactions:
   lines=[dict(x) for x in c.execute('SELECT * FROM invoice_lines WHERE transaction_id=?',(t['id'],))]
   for line in lines:
    ds=[dict(x) for x in c.execute('SELECT * FROM deliveries WHERE line_id=? ORDER BY id',(line['id'],))]
    line['deliveries']=ds
    line['confirmed_qty']=sum(d['qty'] for d in ds if d['creator_ok'] and d['other_ok'])
    line['reserved_qty']=sum(d['qty'] for d in ds)
   t['lines']=lines;t['approved']=bool(t['creator_ok'] and t['other_ok'])
  events=[dict(x) for x in c.execute('SELECT a.*,u.name AS actor_name FROM audit a JOIN users u ON u.id=a.actor_id WHERE a.ledger_id=? ORDER BY a.id DESC LIMIT 100',(lid,))]
  l=dict(l);l['side']=who(l,u['id']);l['opening_approved']=bool(l['opening_creator_ok'] and l['opening_other_ok']);l.pop('invite_token',None)
  balance=l['opening_minor'] if l['opening_approved'] else 0
  for t in transactions:
   if t['approved']:balance+=t['amount_minor']*(1 if t['kind'] in ('debit','invoice') else -1)
  return {'ledger':l,'transactions':transactions,'events':events,'balance_minor':balance}
@app.post('/api/ledgers/{lid}/opening/approve')
def approve_opening(lid:int,u=Depends(user)):
 with db() as c:
  l=ledger(c,lid,u['id']);side=who(l,u['id'])
  if side=='creator':raise HTTPException(409,'You have already approved')
  c.execute('UPDATE ledgers SET opening_other_ok=1 WHERE id=?',(lid,));audit(c,lid,u['id'],'opening.approved',{})
 return {'ok':True}
@app.post('/api/ledgers/{lid}/entries')
def entry(lid:int,x:Entry,u=Depends(user)):
 with db() as c:
  l=ledger(c,lid,u['id'])
  if not(l['opening_creator_ok'] and l['opening_other_ok']):raise HTTPException(409,'Opening balance must be approved first')
  cur=c.execute('INSERT INTO transactions(ledger_id,kind,description,amount_minor,created_by,created_at) VALUES (?,?,?,?,?,?)',(lid,x.kind,x.description,x.amount_minor,u['id'],now()))
  audit(c,lid,u['id'],'entry.proposed',{'transaction_id':cur.lastrowid,'kind':x.kind,'amount_minor':x.amount_minor})
 return {'ok':True}
@app.post('/api/ledgers/{lid}/invoices')
def invoice(lid:int,x:Invoice,u=Depends(user)):
 with db() as c:
  l=ledger(c,lid,u['id'])
  if l['kind']!='supplier':raise HTTPException(400,'Invoices are only for supplier ledgers')
  if not(l['opening_creator_ok'] and l['opening_other_ok']):raise HTTPException(409,'Opening balance must be approved first')
  total=sum(line.amount_minor for line in x.lines)
  cur=c.execute('INSERT INTO transactions(ledger_id,kind,description,amount_minor,created_by,created_at) VALUES (?,?,?,?,?,?)',(lid,'invoice',x.description,total,u['id'],now()))
  tid=cur.lastrowid
  for line in x.lines:c.execute('INSERT INTO invoice_lines(transaction_id,description,qty,amount_minor) VALUES (?,?,?,?)',(tid,line.description,line.qty,line.amount_minor))
  audit(c,lid,u['id'],'invoice.proposed',{'transaction_id':tid,'amount_minor':total})
 return {'ok':True}
@app.post('/api/transactions/{tid}/approve')
def approve_transaction(tid:int,u=Depends(user)):
 with db() as c:
  t=c.execute('SELECT * FROM transactions WHERE id=?',(tid,)).fetchone()
  if not t:raise HTTPException(404,'Transaction not found')
  l=ledger(c,t['ledger_id'],u['id'])
  if t['created_by']==u['id']:raise HTTPException(409,'The other party must approve')
  if t['other_ok']:raise HTTPException(409,'Already approved')
  c.execute('UPDATE transactions SET other_ok=1 WHERE id=?',(tid,))
  audit(c,l['id'],u['id'],'transaction.approved',{'transaction_id':tid})
 return {'ok':True}
@app.post('/api/lines/{line_id}/deliveries')
def propose_delivery(line_id:int,x:Delivery,u=Depends(user)):
 with db() as c:
  row=c.execute('SELECT il.*,t.ledger_id,t.creator_ok,t.other_ok FROM invoice_lines il JOIN transactions t ON t.id=il.transaction_id WHERE il.id=?',(line_id,)).fetchone()
  if not row:raise HTTPException(404,'Line not found')
  l=ledger(c,row['ledger_id'],u['id'])
  if not (row['creator_ok'] and row['other_ok']):raise HTTPException(409,'Approve the invoice first')
  used=c.execute('SELECT COALESCE(SUM(qty),0) AS used FROM deliveries WHERE line_id=?',(line_id,)).fetchone()['used']
  if used+x.qty>row['qty']:raise HTTPException(409,f'Only {row["qty"]-used} unallocated pieces remain')
  cur=c.execute('INSERT INTO deliveries(line_id,qty,created_by,created_at) VALUES (?,?,?,?)',(line_id,x.qty,u['id'],now()))
  audit(c,l['id'],u['id'],'delivery.proposed',{'delivery_id':cur.lastrowid,'qty':x.qty,'line_id':line_id})
 return {'ok':True}
@app.post('/api/deliveries/{did}/approve')
def approve_delivery(did:int,u=Depends(user)):
 with db() as c:
  d=c.execute('SELECT d.*,t.ledger_id FROM deliveries d JOIN invoice_lines i ON i.id=d.line_id JOIN transactions t ON t.id=i.transaction_id WHERE d.id=?',(did,)).fetchone()
  if not d:raise HTTPException(404,'Delivery not found')
  l=ledger(c,d['ledger_id'],u['id'])
  if d['created_by']==u['id']:raise HTTPException(409,'The other party must confirm delivery')
  if d['other_ok']:raise HTTPException(409,'Already confirmed')
  c.execute('UPDATE deliveries SET other_ok=1 WHERE id=?',(did,))
  audit(c,l['id'],u['id'],'delivery.approved',{'delivery_id':did,'qty':d['qty']})
 return {'ok':True}
