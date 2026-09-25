# -*- coding: utf-8 -*-
# MT2Guide - GuideQuestSync.py
# PONTE COM O SISTEMA DE QUESTS DO CLIENTE -> "dados reais da conta/char".
#
# Para que serve (o que o guia ganha com isto):
#   * saber que missoes estao ATIVAS (a meio) -> o guia salta sozinho para
#     a missao em que o jogador esta';
#   * saber quais JA' FORAM FEITAS -> lista marca [x] e filtro "Por fazer";
#   * sincronizar os contadores REAIS do jogo (4/9 caes feitos no jogo);
#   * apanhar o SUBTITULO/descricao real de cada missao (o texto do jogo,
#     em turco) para a pesquisa por nome OU subtitulo.
#
# COMO FUNCIONA (cliente TR/Gameforge) sem depender de nomes fixos da API:
#   1) encontra o modulo python das quests (procurando 'GetQuestCount');
#   2) faz HOOK das funcoes de registo/estado (RegisterQuest, SetQuestTitle,
#      SetQuestFlag, GetQuestCounter, ...) -> aprende os NOMES, TITULOS e
#      CONTADORES reais que o servidor envia, sem sondar nada;
#   3) em paralelo faz POLL de GetQuestName(i)/GetQuestTitle(i)/... (apanha
#      as missoes que ja' estavam ativas antes do guia carregar);
#   4) o estado (feitas / ativas / contadores / titulos) e' gravado em
#      MT2Guide\Saves\<personagem>_quests.txt (sobrevive a reinicios) e
#      MT2Guide\Data\quest_state.txt (ultimo retrato, para diagnostico).
#
# O que NAO faz: nao aceita, nao entrega e nao responde a dialogos. So' le'.
#
# NOTA: a API do modulo de quests muda de cliente para cliente. Por isso
# este ficheiro sonda/varios nomes, faz hook e escreve um DUMP completo da
# API em MT2Guide\Data\api_dump_quest.txt na primeira utilizacao (manda-nos
# esse ficheiro e o helper passa a usar os nomes EXATOS do teu cliente).
import sys

try:
	import __builtin__ as buildin
except ImportError:
	import builtins as buildin

import os
import GuideLib

# tipos de texto/inteiro do python do cliente (2) e do python 3 (testes)
try:
	_STR_TYPES = (str, unicode)
except NameError:
	_STR_TYPES = (str,)
try:
	_INT_TYPES = (int, long)
except NameError:
	_INT_TYPES = (int,)

POLL_EVERY = 2.0        # seg entre sondagens do estado (barato)
SAVE_EVERY = 20.0       # seg entre gravacoes do estado


def _Safe(s):
	try:
		return s or ''
	except:
		return ''


class QuestSync(object):

	# nomes possiveis das funcoes do modulo de quests do cliente
	FN_COUNT = ('GetQuestCount',)
	FN_NAME = ('GetQuestName', 'GetQuestInstanceName', 'GetQuestByName', 'GetQuestIndexName')
	FN_TITLE = ('GetQuestTitle', 'GetQuestInstanceTitle', 'GetQuestNameTitle')
	FN_FLAG = ('GetQuestFlag', 'GetQuestState', 'GetQuestComplete', 'IsQuestComplete')
	FN_COUNTER = ('GetQuestCounter', 'GetQuestCount2', 'GetQuestInstanceCounter')
	FN_CLOCK = ('GetQuestClock', 'GetQuestInstanceClock')

	# nomes possiveis das funcoes que o SERVIDOR chama (hooks de aprendizagem)
	FN_REGISTER = ('RegisterQuest', 'AddQuest', 'OnQuestInfo', 'SetQuestData')
	FN_UNREGISTER = ('UnregisterQuest', 'RemoveQuest', 'DeleteQuest')
	FN_SET_TITLE = ('SetQuestTitle', 'SetQuestName', 'SetQuestInstanceTitle')
	FN_SET_FLAG = ('SetQuestFlag', 'SetQuestState')

	def __init__(self):
		self.mod = None
		self.modName = ''
		self.hooksOn = False
		self._fn = {}            # papel -> (nome, funcao)
		self.enabled = False     # True quando ha' um modulo de quests utilizavel
		self.ready = False
		self.lastPoll = 0.0
		self.lastSave = 0.0
		self.dumped = False

		# --- estado real observado ---
		self.live = {}           # name -> {'title','flag','counter','clock'}
		self.titles = {}         # name.lower() -> melhor titulo conhecido
		self.completed = {}      # name.lower() -> True (missao feita)
		self.raw = {}            # name.lower() -> {'name','title','flag','counter'}
		self.activeName = ''     # nome informado pela ultima resposta de dialogo
		self.log = []            # ultimas linhas de diagnostico

		self.FindModule()
		if self.enabled:
			self.InstallHooks()
			self.DumpOnce()

	# ------------------------------------------------------------ localizar -
	def FindModule(self):
		# procura em sys.modules um modulo com GetQuestCount (o modulo de
		# quests do cliente). Tambem aceita o modulo 'quest' pelo nome.
		for mn, mod in list(sys.modules.items()):
			try:
				if mod is not None and buildin.hasattr(mod, 'GetQuestCount'):
					self.mod = mod
					self.modName = mn
					self.enabled = True
					return
			except:
				pass
		try:
			import quest as _q
			if buildin.hasattr(_q, 'GetQuestCount'):
				self.mod = _q
				self.modName = 'quest'
				self.enabled = True
		except:
			pass

	def _Find(self, names):
		# devolve (nome, funcao) da primeira funcao existente da lista
		for n in names:
			try:
				fn = getattr(self.mod, n, None)
				if buildin.callable(fn):
					return (n, fn)
			except:
				pass
		return None

	def _Resolve(self):
		for role, names in (('count', self.FN_COUNT),
		                    ('name', self.FN_NAME),
		                    ('title', self.FN_TITLE),
		                    ('flag', self.FN_FLAG),
		                    ('counter', self.FN_COUNTER),
		                    ('clock', self.FN_CLOCK),
		                    ('register', self.FN_REGISTER),
		                    ('unregister', self.FN_UNREGISTER),
		                    ('set_title', self.FN_SET_TITLE),
		                    ('set_flag', self.FN_SET_FLAG)):
			if role in self._fn:
				continue
			got = self._Find(names)
			if got is not None:
				self._fn[role] = got

	def Fn(self, role):
		return self._fn.get(role, (None, None))[1]

	def _Call(self, role, *args):
		# chama uma funcao do cliente tentando varias aridades
		fn = self.Fn(role)
		if fn is None:
			return None
		try:
			return fn(*args)
		except TypeError:
			pass
		except Exception:
			return None
		for cut in range(len(args) - 1, 0, -1):
			try:
				return fn(*args[:cut])
			except TypeError:
				continue
			except Exception:
				return None
		return None

	def CallRaw(self, fname, *args):
		# chama uma funcao do modulo pelo nome (tentando aridades)
		try:
			fn = getattr(self.mod, fname, None)
		except:
			fn = None
		if not buildin.callable(fn):
			return None
		for n in range(len(args), -1, -1):
			try:
				return fn(*args[:n])
			except TypeError:
				continue
			except Exception:
				return None
		return None

	# -------------------------------------------------------------- hooks ---
	def InstallHooks(self):
		if self.hooksOn or self.mod is None:
			return
		self.hooksOn = True
		self._Resolve()
		for role in ('register', 'unregister', 'set_title', 'set_flag'):
			pair = self._fn.get(role)
			if pair is None:
				continue
			fname, orig = pair
			try:
				setattr(self.mod, fname, self._MakeHook(role, orig))
				GuideLib.Log('[QuestSync] hook %s.%s' % (self.modName, fname))
			except Exception as e:
				GuideLib.Log('[QuestSync] hook %s ERR: %r' % (fname, e))

	def _MakeHook(self, role, orig):
		def _hook(*args, **kw):
			try:
				self._OnServerCall(role, args)
			except:
				pass
			try:
				return orig(*args, **kw)
			except:
				return None
		return _hook

	def _OnServerCall(self, role, args):
		# o servidor avisou o cliente de algo sobre uma quest
		if role == 'register':
			name = self._FirstStr(args)
			if name:
				self.live[name] = self.live.get(name) or {'title': '', 'flag': None, 'counter': '', 'clock': ''}
				self._Remember(name)
				# quest NOVA no jogo = a que o jogador esta' a fazer agora
				self.activeName = name
				self._ActiveHint()
		elif role == 'unregister':
			name = self._FirstStr(args)
			if name:
				self._OnQuestGone(name)
		elif role == 'set_title':
			name = self._FirstStr(args)
			title = self._SecondStr(args)
			if name and title:
				self.titles[name.lower()] = title
				rec = self.live.get(name)
				if rec is None:
					rec = self.live[name] = {'title': '', 'flag': None, 'counter': '', 'clock': ''}
				rec['title'] = title
				self._Remember(name)
		elif role == 'set_flag':
			name = self._FirstStr(args)
			flag = self._FirstInt(args)
			if name:
				rec = self.live.get(name)
				if rec is None:
					rec = self.live[name] = {'title': '', 'flag': None, 'counter': '', 'clock': ''}
				elif rec.get('flag') is not None and flag != rec.get('flag'):
					# o jogo MUDOU o estado desta quest -> se passou a
					# "feita", fecha-a no guia
					self._OnFlagChange(name, flag)
				rec['flag'] = flag
				self._Remember(name)

	def _FirstStr(self, args):
		for a in args:
			try:
				if buildin.isinstance(a, _STR_TYPES) and len(a) >= 2:
					return str(a)
			except:
				pass
		return ''

	def _SecondStr(self, args):
		found = 0
		for a in args:
			try:
				if buildin.isinstance(a, _STR_TYPES) and len(a) >= 2:
					found += 1
					if found == 2:
						return str(a)
			except:
				pass
		return ''

	def _FirstInt(self, args):
		for a in args:
			try:
				if buildin.isinstance(a, _INT_TYPES) and not buildin.isinstance(a, _STR_TYPES):
					return int(a)
			except:
				pass
		return 0

	# -------------------------------------------------------- poll (sonda) --
	def _RegisteredNames(self):
		# se o modulo tiver uma lista de nomes registados, e' a melhor fonte
		names = None
		for attr in ('GetQuestNameList', 'GetQuestList', 'GetRegisteredQuestList', 'GetQuestNames'):
			try:
				v = getattr(self.mod, attr, None)
				if v is None:
					continue
				if buildin.callable(v):
					v = v()
				if v is not None and not buildin.isinstance(v, (str, unicode)):
					names = list(v)
					break
			except:
				continue
		if names is None:
			return None
		out = []
		for n in names:
			try:
				out.append(str(n))
			except:
				pass
		return out

	def _Num(self, v):
		# devolve v como string (contadores podem vir int, long ou string)
		try:
			if buildin.isinstance(v, _INT_TYPES) and not buildin.isinstance(v, _STR_TYPES):
				return str(int(v))
		except:
			pass
		if buildin.isinstance(v, _STR_TYPES) and v:
			return str(v)
		return ''

	def Poll(self, now):
		if not self.enabled or self.mod is None:
			return
		if now - self.lastPoll < POLL_EVERY:
			return
		self.lastPoll = now
		self._Resolve()
		names = self._RegisteredNames()
		if names is None:
			cnt = self._Call('count')
			try:
				cnt = int(cnt)
			except:
				cnt = 0
			if cnt < 0:
				cnt = 0
			if cnt > 200:
				cnt = 200
			names = []
			for i in range(cnt):
				nm = self._Call('name', i)
				try:
					if buildin.isinstance(nm, _STR_TYPES) and nm:
						names.append(str(nm))
				except:
					pass
		seen = {}
		for nm in names:
			nm = _Safe(nm)
			if not nm:
				continue
			rec = self.live.get(nm)
			if rec is None:
				rec = self.live[nm] = {'title': '', 'flag': None, 'counter': '', 'clock': ''}
			seen[nm] = True
			self._Remember(nm)
			# titulo / subtitulo REAL (em turco) da missao
			if not rec.get('title'):
				t = self._Call('title', nm)
				if not buildin.isinstance(t, _STR_TYPES) or not t:
					t = self.SearchByIndex(nm)   # o nome pode ser um indice
				if buildin.isinstance(t, _STR_TYPES) and t:
					rec['title'] = str(t)
					self.titles[nm.lower()] = str(t)
			# ESTADO da quest: a primeira leitura so' serve de referencia;
			# a partir dai', uma mudanca = o jogo fechou/abriu a quest
			f = self._Call('flag', nm)
			if buildin.isinstance(f, _INT_TYPES) and not buildin.isinstance(f, _STR_TYPES):
				if rec.get('flag') is None:
					rec['flag'] = int(f)
				elif int(f) != rec.get('flag'):
					self._OnFlagChange(nm, f)
					rec['flag'] = int(f)
			# CONTADOR real: le' sempre (muda a cada mob morto/item apanhado)
			c = self._Num(self._Call('counter', nm))
			if c:
				rec['counter'] = c
			self._Remember(nm)   # copia titulo/contador para o retrato 'raw'
		# missoes que SAIRAM do log do jogo
		for nm in list(self.live.keys()):
			if nm not in seen:
				self._OnQuestGone(nm)
		self.ready = True
		if now - self.lastSave > SAVE_EVERY:
			self.lastSave = now
			self._Save()

	# ----------------------------------------------- indice <-> nome ---------
	# Nalguns clientes GetQuestName(i) devolve um id numerico curto e o nome
	# verdadeiro sai por outra funcao (GetQuestIndexName). Sondamos as duas
	# vias para nao perder nada.
	def SearchByIndex(self, maybe_index):
		for attr in ('GetQuestIndexName', 'GetQuestNameByIndex', 'GetQuestTitleByIndex'):
			try:
				fn = getattr(self.mod, attr, None)
				if buildin.callable(fn):
					v = fn(maybe_index)
					if buildin.isinstance(v, _STR_TYPES) and v:
						return str(v)
			except:
				pass
		return ''

	def ProbeNames(self):
		# devolve [(name, title)] de tudo o que o cliente tem AGORA
		out = []
		for nm in list(self.live.keys()):
			rec = self.live[nm]
			out.append((nm, rec.get('title', '')))
		return out

	# ----------------------------------------------------- estado / feitas --
	def _Remember(self, name):
		key = name.lower()
		if key not in self.raw:
			self.raw[key] = {'name': name, 'title': '', 'counter': ''}
		rec = self.live.get(name)
		if rec is not None:
			self.raw[key]['title'] = rec.get('title', '') or self.raw[key]['title']
			self.raw[key]['counter'] = rec.get('counter', '') or self.raw[key]['counter']

	def _FlagIsDone(self, flag):
		# heuristica: na maioria dos clientes 1 = quest concluida,
		# 0 = em curso. Guardamos sempre o valor real no dump para afinar.
		try:
			return int(flag) == 1
		except:
			return False

	def _OnFlagChange(self, name, newflag):
		if self._FlagIsDone(newflag):
			self.completed[name.lower()] = True
			GuideLib.Log('[QuestSync] quest marcada como FEITA pelo jogo: %s' % name)
			self._DoneHint(name)

	def _OnQuestGone(self, name):
		# desapareceu do log do jogo: normalmente = terminada (ou cancelada)
		rec = self.live.pop(name, None)
		key = name.lower()
		done = False
		if rec is not None and self._FlagIsDone(rec.get('flag')):
			done = True
		else:
			# se o guia a estava a seguir, considera-a terminada
			done = True
		if done:
			self.completed[key] = True
			GuideLib.Log('[QuestSync] quest saiu do log do jogo -> feita: %s' % name)
			self._DoneHint(name)

	def _ActiveHint(self):
		fn = getattr(sys, '_mt2guide_activenotify', None)
		if buildin.callable(fn):
			try:
				fn(self.activeName)
			except:
				pass

	def _DoneHint(self, name):
		fn = getattr(sys, '_mt2guide_donenotify', None)
		if buildin.callable(fn):
			try:
				fn(name)
			except:
				pass

	# ----------------------------------------------------------- consultas --
	def IsEnabled(self):
		return bool(self.enabled)

	def IsReady(self):
		return bool(self.ready)

	def TitleOf(self, name):
		return self.titles.get((name or '').lower(), '')

	def CounterOf(self, name):
		key = (name or '').lower()
		rec = self.raw.get(key)
		if rec is None:
			return 0
		return DecodeCounter(rec.get('counter', ''))

	def _Cands(self, name, title=''):
		# nomes/titulos com que a missao do guia pode ser reconhecida
		out = []
		for t in (name, title, self.TitleOf(name)):
			soft = GuideLib.NormalizeText(t)
			if soft:
				out.append(soft)
		return out

	def _LiveSources(self):
		# nomes + TITULOS reais das quests que o jogo tem agora (ativas)
		out = []
		for nm in self.live.keys():
			if nm.lower() in self.completed:
				continue
			out.append(GuideLib.NormalizeText(nm))
			out.append(GuideLib.NormalizeText(self.live[nm].get('title', '')))
		return out

	def _DoneSources(self):
		# nomes + titulos das missões que o jogo guia deu como feitas
		out = []
		for key in self.completed.keys():
			out.append(key)
			rec = self.raw.get(key)
			if rec:
				out.append(GuideLib.NormalizeText(rec.get('name', '')))
				out.append(GuideLib.NormalizeText(rec.get('title', '')))
		return out

	def _MatchAny(self, cands, sources):
		# compara texto normalizado: igual, ou um a conter o outro (nomes
		# longos como "the investigation of the biologist (peach blossom)")
		for c in cands:
			if not c:
				continue
			for s in sources:
				if not s:
					continue
				if c == s:
					return True
				if len(c) > 6 and len(s) > 6 and (c in s or s in c):
					return True
		return False

	def IsCompleted(self, name, title=''):
		if (name or '').lower() in self.completed:
			return True
		return self._MatchAny(self._Cands(name, title), self._DoneSources())

	def IsActive(self, name, title=''):
		if (name or '').lower() in self.completed:
			return False
		if name in self.live:
			return True
		return self._MatchAny(self._Cands(name, title), self._LiveSources())

	def ActiveNames(self):
		return [n for n in self.live.keys() if n.lower() not in self.completed]

	def CompletedNames(self):
		# nomes ORIGINAIS (com maiusculas) das missoes dadas como feitas
		out = []
		for key in self.completed.keys():
			rec = self.raw.get(key)
			out.append((rec or {}).get('name', key))
		return out

	def CompletedCount(self):
		return len(self.completed)

	def KnownCount(self):
		return len(self.live)

	# --------------------------------------------- titulo <-> missao do guia
	def MatchTitles(self, q):
		# devolve a lista de titulos plausiveis desta missao do guia
		out = []
		try:
			if getattr(q, 'name', ''):
				out.append(q.name)
			if getattr(q, 'name_pt', ''):
				out.append(q.name_pt)
			if getattr(q, 'subtitle', ''):
				out.append(q.subtitle)
		except:
			pass
		return out

	def _TitleScore(self, guide_title, game_title):
		# 0..1; compara texto normalizado, palavra a palavra
		a = GuideLib.NormalizeText(guide_title)
		b = GuideLib.NormalizeText(game_title)
		if not a or not b:
			return 0.0
		if a == b:
			return 1.0
		if a in b or b in a:
			return 0.85
		wa = {}
		for w in a.split(' '):
			if len(w) > 3:
				wa[w] = True
		if not wa:
			return 0.0
		hit = 0
		for w in b.split(' '):
			if w in wa:
				hit += 1
		score = float(hit) / float(len(wa))
		if score > 1.0:
			score = 1.0
		return score

	def MatchQuest(self, q):
		# devolve (name, title, score) do registo do JOGO mais parecido
		best = None
		bestScore = 0.0
		titles = self.MatchTitles(q)
		if not titles:
			return None
		for nm in self.live.keys():
			gt = self.live[nm].get('title', '') or nm
			for t in titles:
				s = self._TitleScore(t, gt)
				if s > bestScore:
					bestScore = s
					best = (nm, gt, s)
		if best is None or bestScore < 0.55:
			return None
		return best

	def SubtitleFor(self, q):
		# subtitulo real (texto do jogo) desta missao, se estiver no log
		m = self.MatchQuest(q)
		if m is None:
			return ''
		return m[1]

	# ------------------------------------------------ descoberta de progresso
	def GuessStep(self, q, stepTexts):
		# usa o contador REAL do jogo (ex.: "5" de 9) para acertar no passo
		# atual da missao do guia. Devolve (indice, count) ou None.
		m = self.MatchQuest(q)
		if m is None:
			return None
		name = m[0]
		cnt = self.CounterOf(name)
		if cnt <= 0:
			return None
		# soma os objectivos dos passos (kill/collect) por ordem: o contador
		# do jogo e' cumulativo -> o passo atual e' onde ele cai
		acc = 0
		idx = 0
		for i, need in enumerate(stepTexts):
			if need <= 0:
				idx = i + 1
				continue
			if cnt <= acc + need:
				return (i, cnt - acc)
			acc += need
			idx = i + 1
		return (idx, 0)

	def ResolveActiveQuest(self, quests):
		# devolve o objeto Quest do guia que corresponde a' missao ATIVA no
		# jogo (se houver). Usado para "saltar" para a missao a meio.
		# OTIMIZADO: compara as listas ja' normalizadas (sem repetir
		# NormaliceText 200x por tick).
		if not self.live or not quests:
			return None
		live = []
		for nm in self.live.keys():
			if nm.lower() in self.completed:
				continue
			rec = self.live[nm]
			gt = GuideLib.NormalizeText(rec.get('title', '') or nm)
			gn = GuideLib.NormalizeText(nm)
			live.append((gt, gn))
		if not live:
			return None
		for q in quests:
			cand = getattr(q, 'ntitles', None)
			if not cand:
				cand = [GuideLib.NormalizeText(t) for t in self.MatchTitles(q)]
			if not cand:
				continue
			for c in cand:
				if not c:
					continue
				for (gt, gn) in live:
					if c == gt or c == gn:
						return q
			for c in cand:
				if not c or len(c) <= 6:
					continue
				for (gt, gn) in live:
					if (len(gt) > 6 and (c in gt or gt in c)) or \
					   (len(gn) > 6 and (c in gn or gn in c)):
						return q
		return None

	# ------------------------------------------------------ persistencia ----
	def _SavePath(self):
		try:
			return os.path.join(GuideLib.SavesDir(), _StateFileNames())
		except:
			return None

	def _Save(self):
		try:
			path = self._SavePath()
			if path is None:
				return
			d = os.path.dirname(path)
			if not os.path.isdir(d):
				os.makedirs(d)
			f = open(path, 'w')
			f.write('# MT2Guide - estado das quests (dados REAIS do jogo)\n')
			f.write('# gerado automaticamente; nao e preciso editar\n')
			for key in sorted(self.completed.keys()):
				rec = self.raw.get(key)
				nm = (rec or {}).get('name', key)
				f.write('feita=%s\n' % nm)
			for nm in self.live.keys():
				if nm.lower() in self.completed:
					continue
				rec = self.live[nm]
				f.write('ativa=%s | %s | %s\n' % (nm, rec.get('title', ''), rec.get('counter', '')))
			f.close()
			self._SaveRaw()
		except Exception as e:
			GuideLib.Log('[QuestSync] save ERR: %r' % e)

	def _SaveRaw(self):
		# retrato completo (para diagnostico/debug) em Data/quest_state.txt
		try:
			d = GuideLib.DataDir()
			if not os.path.isdir(d):
				os.makedirs(d)
			f = open(os.path.join(d, 'quest_state.txt'), 'w')
			f.write('# MT2Guide - ultimo retrato do sistema de quests do cliente\n')
			for nm in sorted(self.live.keys()):
				rec = self.live[nm]
				f.write('%s | titulo=%s | flag=%s | contador=%s | feita=%s\n' % (
					nm, rec.get('title', ''), rec.get('flag', ''),
					rec.get('counter', ''),
					'1' if nm.lower() in self.completed else '0'))
			f.close()
		except:
			pass

	def Load(self):
		# recupera as missoes marcadas como feitas em sessoes anteriores
		try:
			path = self._SavePath()
			if path is None or not os.path.exists(path):
				return
			for raw in open(path, 'r').read().splitlines():
				line = raw.strip()
				if line.startswith('feita='):
					nm = line[6:].strip()
					if nm:
						key = nm.lower()
						self.completed[key] = True
						if key not in self.raw:
							self.raw[key] = {'name': nm, 'title': '', 'counter': ''}
			GuideLib.Log('[QuestSync] estado carregado (%d feitas, %d ativas)' % (
				len(self.completed), len(self.live)))
		except:
			pass

	# -------------------------------------------------------------- dump ----
	def DumpOnce(self):
		if self.dumped or self.mod is None:
			return
		self.dumped = True
		try:
			d = GuideLib.DataDir()
			if not os.path.isdir(d):
				os.makedirs(d)
			out = []
			out.append('# MT2Guide - DUMP do modulo de quests do cliente')
			out.append('# modulo: %s' % self.modName)
			attrs = []
			try:
				attrs = sorted(dir(self.mod))
			except:
				pass
			out.append('=== atributos (%d) ===' % len(attrs))
			out.append(', '.join(attrs))
			out.append('')
			out.append('=== funcoes que o guia usa ===')
			for role in self.FN_COUNT + self.FN_NAME + self.FN_TITLE + self.FN_FLAG + \
					self.FN_COUNTER + self.FN_CLOCK + self.FN_REGISTER + \
					self.FN_UNREGISTER + self.FN_SET_TITLE + self.FN_SET_FLAG:
				try:
					if buildin.hasattr(self.mod, role):
						out.append('  %s OK' % role)
				except:
					pass
			out.append('')
			out.append('=== sondagem inicial ===')
			try:
				out.append('  GetQuestCount() = %s' % (self._Call('count'),))
			except:
				pass
			f = open(os.path.join(d, 'api_dump_quest.txt'), 'w')
			f.write('\n'.join(out))
			f.close()
			GuideLib.Log('[QuestSync] api_dump_quest.txt escrito (modulo %s, %d attrs)' % (
				self.modName, len(attrs)))
		except Exception as e:
			GuideLib.Log('[QuestSync] dump ERR: %r' % e)

	def DumpLive(self):
		# .qdump: escreve o estado REAL agora (usado no diagnostico)
		try:
			GuideLib.Log('[QuestSync] modulo=%s enabled=%s ready=%s' % (
				self.modName, self.enabled, self.ready))
			GuideLib.Log('[QuestSync] funcoes: %s' % (
				', '.join(['%s=%s' % (k, v[0]) for k, v in self._fn.items()]),))
			GuideLib.Log('[QuestSync] ativas=%d feitas=%d' % (
				len(self.live), len(self.completed)))
			for nm in sorted(self.live.keys()):
				rec = self.live[nm]
				GuideLib.Log('[QuestSync]  ativa "%s" titulo="%s" flag=%s cont=%s' % (
					nm, rec.get('title', ''), rec.get('flag', ''), rec.get('counter', '')))
			for key in sorted(self.completed.keys()):
				GuideLib.Log('[QuestSync]  feita "%s"' % key)
		except Exception as e:
			GuideLib.Log('[QuestSync] DumpLive ERR: %r' % e)


def DecodeCounter(value):
	# contadores podem vir como int, "3" ou "3/9" -> devolve o numero feito
	if value is None:
		return 0
	try:
		if buildin.isinstance(value, _INT_TYPES) and not buildin.isinstance(value, _STR_TYPES):
			return int(value)
	except:
		pass
	s = str(value)
	for sep in ('/', ','):
		if sep in s:
			s = s.split(sep)[0]
	s = s.strip()
	num = ''
	for ch in s:
		if ch.isdigit():
			num += ch
		else:
			break
	try:
		return int(num)
	except:
		return 0


def _StateFileNames():
	try:
		return GuideLib.StateFileName()
	except:
		return 'estado_quests.txt'


try:
	instance
	instance.__class__ = QuestSync
	instance.enabled = False
	instance.mod = None
	instance.__init__()      # reload-safe: volta a sondar tudo
except NameError:
	instance = QuestSync()
