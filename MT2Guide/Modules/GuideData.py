# -*- coding: utf-8 -*-
# MT2Guide - GuideData.py
# Base de dados de quests + progresso por personagem + gravador de passos.
#
# FORMATO DOS FICHEIROS (MT2Guide/Data/quests_*.txt):
#   [QUEST]
#   name  = Nome da missao (e' o ID unico)
#   map   = mapa interno (ex.: metin2_map_a1; vazio = qualquer mapa)
#   level = nivel recomendado
#   steps:
#     talk    | Nome NPC  | vnum |        | x,y       | texto do passo | 1:Devam
#     kill    | Nome mob  | vnum | count  | x,y       | texto          |
#     collect | Nome item | vnum | count  |           | texto          |
#     goto    |           |      |        | x,y       | texto          |
#     turnin  | Nome NPC  | vnum |        | x,y       | texto          | 1:Kabul Et
#
#   - pos em unidades de pixel do cliente (GetPixelPosition = ingame*100)
#   - POSICOES POR REINO: os NPCs/mobs das cidades 1/2 mudam de sitio
#     conforme o reino. No campo pos podes dar uma posicao por reino:
#         s:62000,63000;c:64000,65000;j:66000,67000
#     (s=Shinsoo/vermelho, c=Chunjo/amarelo, j=Jinno/azul). Uma posicao
#     simples "x,y" aplica-se a todos (mapas comuns: vale, torre, etc.).
#     O GRAVADOR escreve so' a posicao do TEU reino nas cidades 1/2 e
#     posicao comum nos outros mapas.
#   - dialog = "N:Etiqueta" -> N = quadrado a escolher (1 = primeiro)
#   - TIPO DA MISSAO (os filtros do jogo): coluna type, ou dentro do
#     comentario do giver ("# giver: X (main)"), ou pelo nome do ficheiro:
#       type = principal   -> missao principal (main)
#       type = secundaria  -> missao secundaria (side)
#       type = caca        -> MISSAO DE CACA (avlanma gorevi): escolhes 1 de
#                             2 opcoes e tens de matar aquela quantidade
#       type = jogo        -> missao que so' existe no log do jogo (aprendida)
#       type = biologo     -> investigacao do biologo
#       type = cavalo      -> At Gorevleri (cavalo)
#       type = yohara      -> Yohara (Lv120+)
#       type = evento      -> evento
#       type = premium     -> [P] premium
#     Se nao disseres nada o guia DEDUZ o tipo (pelo giver/ficheiro/passos).
#   - SUBTITULO do passo: coluna 8 com tokens, ex.: cat=caca;sub=fala com o X
#   - tudo depois de # e' comentario
import sys
import os

try:
	import __builtin__ as buildin
except ImportError:
	import builtins as buildin

import eXLib
import GuideLib

DATA_DIR = os.path.join(eXLib.PATH, 'MT2Guide', 'Data')
SAVES_DIR = os.path.join(eXLib.PATH, 'MT2Guide', 'Saves')
RECORDED_FILE = os.path.join(DATA_DIR, 'quests_gravadas.txt')

STEP_TYPES = ('talk', 'kill', 'collect', 'goto', 'turnin')

# ------------------------------------------------------------- tipos ------ #
# Os "filtros do jogo": principal / secundaria / caca (gorev de matar) /
# biologo / cavalo / yohara / evento / premium.
TYPE_PRINCIPAL = 'principal'
TYPE_SECUNDARIA = 'secundaria'
TYPE_CACA = 'caca'
TYPE_BIOLOGO = 'biologo'
TYPE_CAVALO = 'cavalo'
TYPE_YOHARA = 'yohara'
TYPE_EVENTO = 'evento'
TYPE_PREMIUM = 'premium'
TYPE_HISTORIA = 'historia'
TYPE_JOGO = 'jogo'      # so' existe no log do jogo (aprendida automaticamente)

TYPE_LABELS = {
	TYPE_PRINCIPAL: 'Principal',
	TYPE_SECUNDARIA: 'Secundaria',
	TYPE_CACA: 'Caca',
	TYPE_JOGO: 'Jogo',
	TYPE_BIOLOGO: 'Biologo',
	TYPE_CAVALO: 'Cavalo',
	TYPE_YOHARA: 'Yohara',
	TYPE_EVENTO: 'Evento',
	TYPE_PREMIUM: 'Premium',
	TYPE_HISTORIA: 'Historia',
}

_TYPE_ALIASES = (
	('principal', TYPE_PRINCIPAL), ('main', TYPE_PRINCIPAL), ('ana', TYPE_PRINCIPAL),
	('historia', TYPE_HISTORIA), ('story', TYPE_HISTORIA),
	('secundaria', TYPE_SECUNDARIA), ('side', TYPE_SECUNDARIA), ('yan', TYPE_SECUNDARIA),
	('caca', TYPE_CACA), ('caza', TYPE_CACA), ('hunt', TYPE_CACA),
	('avlanma', TYPE_CACA), ('gorev', TYPE_CACA), ('matar', TYPE_CACA),
	('biologo', TYPE_BIOLOGO), ('bio', TYPE_BIOLOGO),
	('cavalo', TYPE_CAVALO), ('at', TYPE_CAVALO), ('horse', TYPE_CAVALO),
	('yohara', TYPE_YOHARA),
	('evento', TYPE_EVENTO), ('event', TYPE_EVENTO),
	('premium', TYPE_PREMIUM), ('prem', TYPE_PREMIUM), ('p', TYPE_PREMIUM),
	('jogo', TYPE_JOGO), ('game', TYPE_JOGO),
)

# palavras que indicam "escolhe 1 de 2 opcoes" (missoes de caca)
CHOICE_WORDS = ('escolhe', 'escolher', 'choose', 'select one', 'opcao', 'opcaoo',
                'option', 'ou ', ' or ', 'veya', 'sec', 'choose one')


def ParseType(text):
	# aceita 'main', 'principal', 'caca', 'at', 'Prem'... devolve o tipo canonico
	t = (text or '').strip().lower()
	if not t:
		return ''
	for alias, canon in _TYPE_ALIASES:
		if t.startswith(alias):
			return canon
	return ''


def TypeLabel(t):
	return TYPE_LABELS.get(t, t or '?')


def FileDefaultType(filename):
	# tipo por omissao conforme o nome do ficheiro quests_*.txt
	f = (filename or '').lower()
	if 'premium' in f or 'prem' in f:
		return TYPE_PREMIUM
	if 'yohara' in f:
		return TYPE_YOHARA
	if 'extra' in f or 'cavalo' in f or 'at_' in f:
		return TYPE_CAVALO
	if 'evento' in f or 'event' in f:
		return TYPE_EVENTO
	return ''


class HuntOpt:
	# UMA opcao de uma MISSAO DE CACA ("escolhe 1 de 2"):
	#   idx   = 1 ou 2 (o numero que aparece na janela do jogo)
	#   count = quantos mobs dessa opcao
	#   name  = nome do mob (nome do cliente)
	#   vnum  = codigo do mob (0 = ainda NAO sabemos; o guia aprende
	#           em jogo e guarda em Data/mobs_vnum.txt)
	__slots__ = ('idx', 'count', 'name', 'vnum')

	def __init__(self, idx=1, count=0, name='', vnum=0):
		self.idx = idx
		self.count = count
		self.name = name
		self.vnum = vnum

	def Label(self):
		nm = self.name or ('vnum %d' % self.vnum if self.vnum else 'mob')
		return '%dx %s' % (self.count or 0, nm)

	def Short(self):
		# etiqueta curta para a linha de dica (cabe na janela)
		return '[%d] %s' % (self.idx, self.Label())


class Step:
	__slots__ = ('type', 'name', 'vnum', 'vnums', 'count', 'x', 'y', 'kpos', 'plist', 'pmap', 'text', 'dlg_num', 'dlg_label', 'cat', 'sub', 'opts')

	def __init__(self):
		self.type = 'goto'
		self.name = ''
		self.vnum = 0
		self.vnums = []     # varios mobs ACEITES no mesmo passo (escolhe 1 de 2)
		self.count = 0
		self.x = None
		self.y = None
		self.kpos = {}    # {1:(x,y) shinsoo, 2:(...) chunjo, 3:(...) jinno} (1a pos)
		self.plist = []   # [(x, y), ...] posicoes comuns (varias zonas)
		self.pmap = {}    # {1:[(x,y),...], 2:[...], 3:[...]} por reino
		self.text = ''
		self.dlg_num = 0
		self.dlg_label = ''
		self.cat = ''        # categoria do passo (coluna 8: cat=caca)
		self.sub = ''        # subtitulo/dica do passo (coluna 8: sub=...)
		self.opts = []       # opcoes 1 de 2 (coluna 8: op1=10:Nome;op2=5:Nome)

	def HasPos(self):
		return self.x is not None and self.y is not None

	def IsCountStep(self):
		# passo que conta mortes/items (kill = matar, collect = apanhar)
		return self.type in ('kill', 'collect')

	def HuntOptions(self):
		# OPCOES deste passo (missao de caca "escolhe 1 de 2"). Se o
		# ficheiro so' deu vnums ("101,107") sem nomes, fabrica as opcoes
		# a partir deles para tudo o resto continuar a funcionar.
		if self.opts:
			return list(self.opts)
		vs = list(self.vnums)
		if len(vs) < 2:
			return []
		out = []
		for i, v in enumerate(vs):
			out.append(HuntOpt(i + 1, self.count, self.name, v))
		return out

	def OptionOf(self, idx):
		# opcao numero idx (1/2); None se nao existir
		try:
			idx = int(idx)
		except Exception:
			return None
		for o in self.HuntOptions():
			if o.idx == idx:
				return o
		return None

	def OptionCount(self, idx):
		# quantos mobs desta opcao (cai no count do passo se nao disser)
		o = self.OptionOf(idx)
		if o is not None and o.count:
			return o.count
		if o is not None and self.count:
			return self.count
		return o.count if o is not None else self.count

	def HuntVnums(self):
		# TODOS os mobs candidatos deste passo. Nas MISSOES DE CACA
		# ("escolhe 1 de 2") ficam aqui os dois/va'rios: qualquer um
		# pode contar, mas so' o escolhido leva a MIRA VERMELHA.
		out = list(self.vnums)
		for o in self.opts:
			if o.vnum and o.vnum not in out:
				out.append(o.vnum)
		if not out and self.vnum:
			out = [self.vnum]
		return out

	def HuntNames(self):
		return [o.name for o in self.HuntOptions() if o.name]

	def IsHunt(self):
		# passo de caca com ESCOLHA entre mobs (2+ opcoes)
		return self.IsCountStep() and len(self.HuntOptions()) > 1

	def HuntText(self):
		# texto que DIZ O MOB DE CADA OPCAO (mostrado no passo atual)
		# ex.: ESCOLHE 1 DE 2:  [1] 10x Cao Selvagem Feroz  ou  [2] 5x Lobo Feroz
		opts = self.HuntOptions()
		if len(opts) < 2:
			return ''
		parts = []
		for o in opts:
			parts.append('[%d] mata %s' % (o.idx, o.Label()))
		return 'ESCOLHE 1 DE 2: ' + '  ou  '.join(parts)

	def _all_points(self):
		out = []
		for pts in self.pmap.values():
			out.extend(pts)
		out.extend(self.plist)
		return out

	def BestPoint(self, kingdom, mx=None, my=None):
		# melhor posicao: pontos do reino atual (senao comuns); escolhe o
		# ponto MAIS PERTO do jogador quando ha varios (zonas de spawn)
		pts = []
		if kingdom and kingdom in self.pmap:
			pts = list(self.pmap[kingdom])
		if not pts:
			pts = list(self.plist)
		if not pts:
			# compat: kpos unico / pos geral
			if kingdom and kingdom in self.kpos:
				return self.kpos[kingdom]
			if self.HasPos():
				return (self.x, self.y)
			for v in self.kpos.values():
				return v
			return None
		if mx is None or my is None or len(pts) == 1:
			return pts[0]
		best = pts[0]
		bd = 1e18
		for (px, py) in pts:
			d = (px - mx) * (px - mx) + (py - my) * (py - my)
			if d < bd:
				bd = d
				best = (px, py)
		return best

	def PosForKingdom(self, kingdom):
		# compat: posicao do reino pedido; fallback: geral / 1a disponivel
		if kingdom and kingdom in self.kpos:
			return self.kpos[kingdom]
		if self.pmap:
			for k in (kingdom, 1, 2, 3):
				if k in self.pmap and self.pmap[k]:
					return self.pmap[k][0]
		if self.plist:
			return self.plist[0]
		if self.HasPos():
			return (self.x, self.y)
		try:
			for v in self.kpos.values():
				return v
		except:
			pass
		return None

	def DialogHint(self):
		if self.dlg_num > 0:
			tag = '[%d] %s' % (self.dlg_num, self.dlg_label) if self.dlg_label else ('[%d]' % self.dlg_num)
			return 'DIALOGO: escolhe o quadrado %s' % tag
		return ''


class Quest:
	__slots__ = ('name', 'name_pt', 'map', 'level', 'steps', 'type', 'giver',
	             'subtitle', 'chapter', 'source', 'ntitles')

	def __init__(self):
		self.name = ''
		self.name_pt = ''   # titulo em portugues (pesquisa/mostracao)
		self.map = ''
		self.level = 0
		self.steps = []
		self.type = ''      # principal/secundaria/caca/... (filtros do jogo)
		self.giver = ''     # quem da' a missao (NPC)
		self.subtitle = ''  # subtitulo/descricao (pesquisa)
		self.chapter = ''   # subtitulo REAL vindo do jogo (GuideQuestSync)
		self.source = ''    # ficheiro de onde veio (diagnostico)
		self.ntitles = []   # titulos normalizados (pesquisa/comparacao rapida)

	def Kind(self, stepIdx=0):
		# tipo a mostrar: tipo da missao; nos passos com categoria propria
		# (ex.: a parte de caca de uma quest secundaria) usa a do passo
		if 0 <= stepIdx < len(self.steps):
			cat = getattr(self.steps[stepIdx], 'cat', '')
			if cat:
				return cat
		if self.type:
			return self.type
		return TYPE_SECUNDARIA

	def KindLabel(self, stepIdx=0):
		return TypeLabel(self.Kind(stepIdx))

	def IsHunt(self):
		# MISSAO DE CACA: escolhe 1 de 2 mobs e mata X de um deles
		if self.type == TYPE_CACA:
			return True
		for st in self.steps:
			if st.IsHunt():
				return True
		return False

	def HuntStep(self, stepIdx=0):
		# o passo do atual que e' de caca com escolha (senao None)
		if 0 <= stepIdx < len(self.steps) and self.steps[stepIdx].IsHunt():
			return self.steps[stepIdx]
		for st in self.steps:
			if st.IsHunt():
				return st
		return None

	def HuntLabel(self, stepIdx=0):
		# texto para o detalhe: DIZ QUAIS OS MOBS DE CADA OPCAO
		st = self.HuntStep(stepIdx)
		if st is None:
			return ''
		opts = st.HuntOptions()
		if len(opts) > 1:
			parts = ['[%d] %s' % (o.idx, o.Label()) for o in opts]
			return 'CACA (escolhe 1 de 2): ' + '  ou  '.join(parts)
		vs = st.HuntVnums()
		return 'CACA: mata %d (%s) - vnum %s' % (
			st.count or 0, st.name or 'mob', ','.join([str(v) for v in vs]))

	def SearchText(self):
		# tudo o que a pesquisa pode usar: nome, nome PT, subtitulo, giver e
		# o texto de TODOS os passos (objetivos)
		parts = [self.name, self.name_pt, self.subtitle, self.giver,
			 TypeLabel(self.type), self.chapter]
		for st in self.steps:
			parts.append(st.text)
			parts.append(st.name)
			parts.append(st.sub)
			# NOMES DOS MOBS DE CADA OPCAO (missoes de caca): a pesquisa
			# por "cao selvagem feroz" tem de encontrar a missao
			for o in st.opts:
				parts.append(o.name)
		return ' | '.join([p for p in parts if p])


def _ParseKingdomLetter(k):
	# s/shinsoo -> 1, c/chunjo -> 2, j/jinno -> 3
	k = (k or '').strip().lower()
	if k.startswith('s'):
		return 1
	if k.startswith('c'):
		return 2
	if k.startswith('j'):
		return 3
	return 0


def _ParseExtra(extra, key):
	# coluna 8: tokens "cat=caca;sub=fala com o X" (ou so' texto -> sub)
	extra = (extra or '').strip()
	if not extra:
		return ''
	for tok in extra.split(';'):
		tok = tok.strip()
		if not tok:
			continue
		if '=' in tok:
			k, _, v = tok.partition('=')
			if k.strip().lower() in (key, key[:3]):
				return v.strip()
		elif key == 'sub':
			return tok
	return ''


def _ParseHuntOpts(st, extra):
	# COLUNA 8 das MISSOES DE CACA ("escolhe 1 de 2"):
	#   cat=caca;op1=10:Cao Selvagem Feroz;op2=5:Lobo Feroz
	# tambem aceita o vnum no fim do token (quando ja' se sabe):
	#   op1=10:Cao Selvagem Feroz:101
	for tok in (extra or '').split(';'):
		tok = tok.strip()
		low = tok.lower()
		if not (low.startswith('op') or low.startswith('opt')):
			continue
		head, sep, val = tok.partition('=')
		if not sep:
			continue
		idx = head.lower().replace('opt', '').replace('op', '').strip()
		if not idx.isdigit():
			continue
		segs = val.split(':')
		opt = HuntOpt(int(idx), 0, '', 0)
		if len(segs) >= 2:
			try:
				opt.count = int(segs[0].strip())
			except ValueError:
				opt.count = 0
			opt.name = segs[1].strip()
			if len(segs) >= 3:
				try:
					opt.vnum = int(segs[2].strip())
				except ValueError:
					opt.vnum = 0
		else:
			opt.name = val.strip()
		st.opts.append(opt)
	st.opts.sort(key=lambda o: o.idx)


def _ParseStep(line):
	parts = [p.strip() for p in line.split('|')]
	while len(parts) < 7:
		parts.append('')
	st = Step()
	st.type = parts[0].lower()
	if st.type not in STEP_TYPES:
		return None
	st.name = parts[1]
	# vnum: um mob ou VARIOS (missoes de caca: "escolhe 1 de 2" -> 101,107)
	for tok in (parts[2] or '').replace(';', ',').split(','):
		tok = tok.strip()
		if not tok:
			continue
		try:
			st.vnums.append(int(tok))
		except:
			pass
	st.vnum = st.vnums[0] if st.vnums else 0
	try:
		st.count = 0
	except:
		pass
	try:
		st.count = int(parts[3]) if parts[3] else 0
	except:
		st.count = 0
	if parts[4]:
		# pos: "x,y" (comum) ou "s:x,y;c:x,y;j:x,y" (por reino). ACEITA
		# VARIOS pontos por reino/mapa: "s:x,y;s:x,y;c:x,y;x,y;x,y" ->
		# o guia escolhe o ponto MAIS PERTO do jogador (zonas de spawn)
		for seg in parts[4].split(';'):
			seg = seg.strip()
			if not seg:
				continue
			try:
				if ':' in seg:
					kk, _, coords = seg.partition(':')
					ki = _ParseKingdomLetter(kk)
					px, py = coords.split(',')
					pt = (float(px), float(py))
					st.pmap.setdefault(ki, []).append(pt)
					if ki not in st.kpos:
						st.kpos[ki] = pt
				else:
					px, py = seg.split(',')
					pt = (float(px), float(py))
					st.plist.append(pt)
					if st.x is None:
						st.x = pt[0]
						st.y = pt[1]
			except:
				pass
	st.text = parts[5]
	if parts[6]:
		try:
			n, _, lbl = parts[6].partition(':')
			st.dlg_num = int(n)
			st.dlg_label = lbl
		except:
			st.dlg_label = parts[6]
	if len(parts) > 7:
		st.cat = ParseType(_ParseExtra(parts[7], 'cat'))
		st.sub = _ParseExtra(parts[7], 'sub')
		_ParseHuntOpts(st, parts[7])
	if not st.vnums and st.vnum:
		st.vnums = [st.vnum]
	return st


def _ReadText(path):
	try:
		f = open(path, 'r')
		data = f.read()
		f.close()
		return data
	except:
		return ''


def _ParseGiverHint(text):
	# "# giver: Seyis - precisa de X"  /  "# giver: AUTO (main)"
	# devolve (quemDa, tipo) -> tipo pode ser '' se o comentario nao disser
	s = (text or '').strip()
	low = s.lower()
	out = ''
	for tag, canon in (('(main)', TYPE_PRINCIPAL), ('(principal)', TYPE_PRINCIPAL),
	                   ('(side)', TYPE_SECUNDARIA), ('(secundaria)', TYPE_SECUNDARIA),
	                   ('(caca)', TYPE_CACA), ('(hunt)', TYPE_CACA),
	                   ('(biologo)', TYPE_BIOLOGO), ('(bio)', TYPE_BIOLOGO),
	                   ('(cavalo)', TYPE_CAVALO), ('(horse)', TYPE_CAVALO),
	                   ('(yohara)', TYPE_YOHARA), ('(evento)', TYPE_EVENTO),
	                   ('(premium)', TYPE_PREMIUM), ('(historia)', TYPE_HISTORIA)):
		if tag in low:
			out = canon
			s = s[:low.index(tag)].strip()
			low = s.lower()
			break
	nm = s
	for sep in (' - ', ' -- ', ';'):
		if sep in nm:
			nm = nm.split(sep)[0]
	nm = nm.strip().strip('(').strip()
	return (nm, out)


def ParseQuestText(text, defaultType='', source=''):
	quests = []
	cur = None
	in_steps = False

	def _flush():
		if cur is not None and cur.name and cur.steps:
			_FinalizeQuest(cur)
			quests.append(cur)

	def _FinalizeQuest(q):
		# completa o que nao veio no ficheiro: tipo do jogo + subtitulo
		if not q.type:
			q.type = defaultType
		if not q.type:
			q.type = _GuessType(q)
		# MISSAO DE CACA: a wiki marca quase tudo como principal/secundaria,
		# mas as missoes em que SO' se mata/aparece sao de CACA (avlanma)
		if q.type in (TYPE_PRINCIPAL, TYPE_SECUNDARIA) and _IsPureHunt(q):
			q.type = TYPE_CACA
		if not q.subtitle and q.chapter:
			q.subtitle = q.chapter
		# titulos normalizados (comparar com o jogo sem acentos/maiusculas)
		try:
			seen = {}
			for t in (q.name, q.name_pt, q.subtitle, q.chapter, q.giver):
				n = GuideLib.NormalizeText(t)
				if n and n not in seen:
					seen[n] = True
					q.ntitles.append(n)
		except Exception as e:
			GuideLib.Log('[GuideData] ntitles ERR (%s): %r' % (q.name, e))

	for raw in text.splitlines():
		line = raw.strip()
		if not line:
			continue
		if line.startswith('#'):
			# comentario: pode conter o giver e o TIPO da missao
			if cur is not None and not in_steps:
				low = line.lstrip('#').strip().lower()
				if low.startswith('giver') or low.startswith('tipo') or low.startswith('type'):
					val = line.lstrip('#').strip().partition(':')[2]
					giver, tipo = _ParseGiverHint(val)
					if giver and not cur.giver:
						cur.giver = giver
					if tipo and not cur.type:
						cur.type = tipo
			continue
		if line.lower() == '[quest]':
			_flush()
			cur = Quest()
			cur.source = source
			in_steps = False
			continue
		if cur is None:
			continue
		if line.lower().startswith('steps'):
			in_steps = True
			continue
		if in_steps:
			st = _ParseStep(line)
			if st is not None:
				cur.steps.append(st)
			continue
		if '=' in line:
			k, _, v = line.partition('=')
			k = k.strip().lower()
			v = v.strip()
			if k == 'name':
				cur.name = v
			elif k == 'name_pt':
				cur.name_pt = v
			elif k == 'map':
				cur.map = v
			elif k == 'type' or k == 'tipo':
				cur.type = ParseType(v) or v.lower()
			elif k == 'giver':
				cur.giver = v
			elif k == 'subtitle' or k == 'subtitulo':
				cur.subtitle = v
			elif k == 'chapter' or k == 'capitulo':
				cur.chapter = v
			elif k == 'level':
				try:
					cur.level = int(v)
				except:
					cur.level = 0
	_flush()
	return quests


def _IsPureHunt(q):
	# a missao so' pede matar/apanhar (com passos de caminho pelo meio)?
	# -> e' uma MISSAO DE CACA
	if not q.steps:
		return False
	kills = 0
	for st in q.steps:
		if st.IsCountStep():
			kills += 1
		elif st.type != 'goto':
			return False
	return kills > 0


def _GuessType(q):
	# deduz o tipo do jogo quando o ficheiro nao diz nada:
	#   [P]                    -> premium
	#   escolhe 1 de 2 + matar -> CACA (avlanma gorevi)
	#   so' matar/apanhar       -> CACA
	#   so' falar               -> historia
	#   resto                   -> secundaria
	try:
		if q.name.startswith('[P]'):
			return TYPE_PREMIUM
		if 'yohara' in q.name.lower():
			return TYPE_YOHARA
		if 'cavalo' in q.name.lower() or q.name.lower().startswith('at '):
			return TYPE_CAVALO
		if 'biolog' in q.name.lower():
			return TYPE_BIOLOGO
	except:
		pass
	kills = 0
	others = 0
	choice = False
	for st in q.steps:
		if st.type in ('kill', 'collect'):
			kills += 1
			# MISSAO DE CACA: escolhe 1 de 2 opcoes de mob
			#   - passo com 2 vnums aceites (101,107)
			#   - texto do passo a dizer "... ou ..." / "... or ..."
			if len(st.vnums) > 1 or st.IsHunt() or _HasChoice(st.text) or _HasChoice(st.sub):
				choice = True
		else:
			others += 1
	if kills and (choice or not others):
		# CACA: escolhe 1 de 2 mobs  OU  missao so' de matar/apanhar
		return TYPE_CACA
	if not kills:
		return TYPE_HISTORIA
	return TYPE_SECUNDARIA


def _HasChoice(text):
	# o passo diz que ha' uma ESCOLHA entre opcoes (1 de 2)?
	low = (text or '').lower()
	for w in CHOICE_WORDS:
		if w in low:
			return True
	return False


# ------------------------------------------- vnums APRENDIDOS dos mobs -----
# As missoes de caca dizem o NOME do mob ("Cao Selvagem Feroz") mas o nome
# do vnum nao vem em nenhum ficheiro do cliente que possamos ler. Por isso o
# guia APRENDE em jogo: quando mata/trava um mob e o cliente diz o nome dele,
# fica guardado aqui (Data/mobs_vnum.txt) e nas proximas sessoes a MIRA ja'
# sabe apontar pelo vnum, sem depender do nome.
MOB_VNUMS = {}      # nome normalizado -> vnum
_MOB_LOADED = [False]


def MobVnumPath():
	return os.path.join(DATA_DIR, 'mobs_vnum.txt')


def LoadMobVnums(force=False):
	if _MOB_LOADED[0] and not force:
		return len(MOB_VNUMS)
	_MOB_LOADED[0] = True
	try:
		path = MobVnumPath()
		if not os.path.exists(path):
			return 0
		for raw in open(path, 'r').read().splitlines():
			line = raw.strip()
			if not line or line.startswith('#') or '|' not in line:
				continue
			v, _, nm = line.partition('|')
			try:
				vnum = int(v.strip())
			except ValueError:
				continue
			n = GuideLib.NormalizeText(nm)
			if vnum > 0 and n:
				MOB_VNUMS[n] = vnum
		GuideLib.Log('[GuideData] %d vnums de mobs aprendidos' % len(MOB_VNUMS))
	except Exception as e:
		GuideLib.Log('[GuideData] LoadMobVnums ERR: %r' % e)
	return len(MOB_VNUMS)


def _SaveMobVnums():
	try:
		if not os.path.isdir(DATA_DIR):
			os.makedirs(DATA_DIR)
		f = open(MobVnumPath(), 'w')
		f.write('# MT2Guide - vnum de cada mob, APRENDIDO em jogo\n')
		f.write('# formato: vnum|nome   (nao e preciso editar)\n')
		for n in sorted(MOB_VNUMS.keys()):
			f.write('%d|%s\n' % (MOB_VNUMS[n], n))
		f.close()
	except Exception as e:
		GuideLib.Log('[GuideData] _SaveMobVnums ERR: %r' % e)


def MobVnumByName(name):
	# vnum do mob pelo NOME (0 = ainda nao sabemos)
	n = GuideLib.NormalizeText(name)
	if not n or len(n) < 3:
		return 0
	v = MOB_VNUMS.get(n)
	if v:
		return v
	# nomes do cliente podem ter prefixos/sufixos ("[Feroz] Cao...")
	# -> aceita contencao quando o nome e' suficientemente longo
	best = 0
	for k, vv in MOB_VNUMS.items():
		if len(k) >= 6 and (n in k or k in n):
			best = vv
	return best


def MobNameByVnum(vnum):
	try:
		vnum = int(vnum)
	except Exception:
		return ''
	for k, v in MOB_VNUMS.items():
		if v == vnum:
			return k
	return ''


def LearnMobVnum(name, vnum):
	# "este vnum e' este mob" -> guarda para sempre (por instalacao)
	if not name or not vnum:
		return False
	n = GuideLib.NormalizeText(name)
	if not n or len(n) < 3:
		return False
	try:
		vnum = int(vnum)
	except Exception:
		return False
	if vnum <= 0:
		return False
	if MOB_VNUMS.get(n) == vnum:
		return False
	MOB_VNUMS[n] = vnum
	_SaveMobVnums()
	GuideLib.Log('[GuideData] mob aprendido: "%s" = vnum %d' % (n, vnum))
	return True


def _AttachMobVnums(quests):
	# completa as opcoes sem vnum com o que o guia ja' aprendeu em jogo
	n = 0
	for q in quests:
		for st in q.steps:
			for o in st.opts:
				if o.vnum:
					continue
				v = MobVnumByName(o.name)
				if v:
					o.vnum = v
					n += 1
	if n:
		GuideLib.Log('[GuideData] %d opcoes de caca ficaram COM vnum (aprendido)' % n)
	return n


def LoadAllQuests():
	files = []
	try:
		for fn in sorted(os.listdir(DATA_DIR)):
			if fn.startswith('quests_') and fn.endswith('.txt'):
				files.append(fn)
	except:
		pass
	all_q = []
	for fn in files:
		all_q.extend(ParseQuestText(_ReadText(os.path.join(DATA_DIR, fn)),
		                            FileDefaultType(fn), fn))
	# MISSOES DE CACA: os mobs "Feroz"/"Mau"/"Elite" nao existem em nenhum
	# ficheiro que possamos ler -> completa-os com os vnums APRENDIDOS em jogo
	try:
		LoadMobVnums()
		_AttachMobVnums(all_q)
	except Exception as e:
		GuideLib.Log('[GuideData] attach vnums ERR: %r' % e)
	GuideLib.Log('[GuideData] %d missoes de %d ficheiros' % (len(all_q), len(files)))
	return all_q


def CountByType(quests):
	out = {}
	for q in quests:
		t = q.type or TYPE_SECUNDARIA
		out[t] = out.get(t, 0) + 1
	return out


# ------------------------------------------------------------- progresso --
class Progress:
	# PROGRESSO POR PERSONAGEM (Saves\<personagem>.txt).
	# O contador de MORTES/ITEMS de cada passo fica gravado com a chave
	# "missao|passo" -> se matares 5 de 10 e SAIRES DO JOGO, quando voltares
	# o guia continua de 5 (o trabalho nao se perde; tambem e' assim por
	# personagem, cada char tem o seu ficheiro).
	def __init__(self):
		self.quest = ''      # nome (ID) da quest ativa
		self.step = 0        # indice do passo atual
		self.kills = {}      # "missao|passo" -> contador (PERSISTENTE)
		self.choice = {}     # "missao|passo" -> vnum do mob escolhido (caca 1 de 2)
		self.char = ''       # personagem a que este progresso pertence
		self.Reset()

	def Reset(self):
		# muda de missao/passo: NAO apaga self.kills/self.choice (o
		# progresso de cada passo tem de sobreviver a sair do jogo e a
		# andar para a frente e para tras na lista de passos)
		self.quest = ''
		self.step = 0

	# ----------------------------------------------- contador por passo ---
	def StepKey(self, quest=None, step=None):
		q = self.quest if quest is None else quest
		s = self.step if step is None else step
		try:
			s = int(s)
		except:
			s = 0
		return '%s|%d' % (q, s)

	@property
	def killed(self):
		# contador REAL do passo atual (vem do ficheiro do personagem)
		return self.kills.get(self.StepKey(), 0)

	@killed.setter
	def killed(self, n):
		# compatibilidade: "self.progress.killed = N" continua a funcionar
		self.SetStepCount(n)

	def StepCount(self, quest=None, step=None):
		return self.kills.get(self.StepKey(quest, step), 0)

	def SetStepCount(self, n, quest=None, step=None, save=True):
		k = self.StepKey(quest, step)
		if not k.split('|')[0]:
			return 0                 # sem missao -> nao guarda lixo
		try:
			n = int(n)
		except:
			n = 0
		if n < 0:
			n = 0
		if n != self.kills.get(k, 0):
			if n:
				self.kills[k] = n
				self._Trim()
			else:
				# contador a zero -> o mob escolhido tambem deixa de contar
				self.kills.pop(k, None)
				self.choice.pop(k, None)
			if save:
				self.Save()
		return self.kills.get(k, 0)

	def AddStepCount(self, n=1, quest=None, step=None):
		# soma e GRAVA ja' (se o jogador sair do jogo a seguir, fica salvo)
		k = self.StepKey(quest, step)
		return self.SetStepCount(self.kills.get(k, 0) + int(n), quest, step)

	def ChoiceOf(self, quest=None, step=None):
		# TOKEN da escolha deste passo: 'op1'/'op2' (numero da opcao das
		# missoes de caca "1 de 2") ou o VNUM do mob (passos antigos).
		# 0 = o jogador ainda nao disse qual escolheu.
		try:
			v = self.choice.get(self.StepKey(quest, step), 0)
		except Exception:
			v = 0
		return v or 0

	def ChoiceIndex(self, quest=None, step=None):
		# 1/2 = numero da opcao escolhida (0 = ainda nao sabemos)
		try:
			s = self.ChoiceOf(quest, step)
		except Exception:
			s = 0
		if isinstance(s, str):
			s = s.replace('op', '').replace('opt', '').strip() or '0'
		try:
			n = int(s)
		except Exception:
			return 0
		if 1 <= n <= 9:
			return n
		return 0

	def ChoiceVnum(self, quest=None, step=None):
		# VNUM do mob escolhido (passos com 2 vnums e sem nomes)
		try:
			n = int(self.ChoiceOf(quest, step))
		except Exception:
			return 0
		if n > 9:
			return n
		return 0

	def SetChoice(self, value, quest=None, step=None):
		# value: numero da opcao ('op1'/1), vnum do mob (101) ou '' (limpa)
		k = self.StepKey(quest, step)
		if not k.split('|')[0]:
			return 0
		try:
			v = int(value)
		except Exception:
			s = str(value or '').strip().lower()
			if not s:
				return 0
			v = s
		if v != self.choice.get(k, 0):
			self.choice[k] = v
			self.Save()
			GuideLib.Log('[Progress] escolha=%s para %s' % (v, k))
		return self.choice.get(k, 0)

	def _Trim(self, limit=500):
		# nao deixa o ficheiro do personagem crescer para sempre
		try:
			if len(self.kills) <= limit:
				return
			keep = self.StepKey()
			for k in list(self.kills.keys()):
				if len(self.kills) <= limit:
					break
				if k != keep:
					del self.kills[k]
					self.choice.pop(k, None)
		except:
			pass

	def Save(self):
		try:
			if not os.path.isdir(SAVES_DIR):
				os.makedirs(SAVES_DIR)
			safe = GuideLib.SafeCharName()
			self.char = safe
			path = os.path.join(SAVES_DIR, safe + '.txt')
			f = open(path, 'w')
			f.write('# MT2Guide - progresso de %s (nao apagar a mao)\n' % safe)
			f.write('quest=%s\n' % self.quest)
			f.write('step=%d\n' % self.step)
			f.write('killed=%d\n' % self.killed)
			f.write('# mortes/items por passo: kill=missao|passo|contador\n')
			for k, c in self.kills.items():
				f.write('kill=%s|%d\n' % (k, c))
			for k, v in self.choice.items():
				f.write('escolha=%s|%s\n' % (k, v))
			f.close()
		except Exception as e:
			GuideLib.Log('[GuideData] save ERR: %r' % e)

	def Load(self):
		self.kills = {}
		self.choice = {}
		legacy = None
		try:
			safe = GuideLib.SafeCharName()
			self.char = safe
			path = os.path.join(SAVES_DIR, safe + '.txt')
			if not os.path.exists(path):
				return False
			for raw in open(path, 'r').read().splitlines():
				line = raw.strip()
				if not line or line.startswith('#') or '=' not in line:
					continue
				k, _, v = line.partition('=')
				if k == 'quest':
					self.quest = v
				elif k == 'step':
					try:
						self.step = int(v)
					except:
						pass
				elif k == 'killed':
					legacy = v          # formato antigo: sem chave
				elif k == 'kill':
					key, _, cnt = v.rpartition('|')
					if key:
						try:
							n = int(cnt)
						except:
							n = 0
						if n > 0:
							self.kills[key] = n
				elif k == 'escolha':
					key, _, ch = v.rpartition('|')
					ch = ch.strip()
					try:
						ch = int(ch)
					except ValueError:
						pass
					if key and ch:
						self.choice[key] = ch
			if legacy is not None:
				try:
					n = int(legacy)
				except:
					n = 0
				cur = self.kills.get(self.StepKey(), 0)
				if n > cur:
					self.kills[self.StepKey()] = n
			self._Trim()
			return bool(self.quest)
		except:
			return False


# ---------------------------------------------- missoes JA' FEITAS (guia) --
# Registo por personagem das missoes que o guia deu por concluidas (quando
# chegas ao ultimo passo) + as que o JOGO disse (GuideQuestSync). Fica em
# MT2Guide\Saves\<personagem>_feitas.txt -> a quest line marca-as [x] e o
# filtro "A fazer" esconde-as.
class DoneLog:
	def __init__(self):
		self.done = {}          # nome->titulo original (chave normalizada)
		self.Path = None
		self.Load()

	def _Path(self):
		try:
			return os.path.join(GuideLib.SavesDir(), GuideLib.SafeCharName() + '_feitas.txt')
		except:
			return None

	def Load(self):
		try:
			self.done = {}
		except:
			pass
		try:
			path = self._Path()
			if path is None or not os.path.exists(path):
				return
			for raw in open(path, 'r').read().splitlines():
				line = raw.strip()
				if not line or line.startswith('#'):
					continue
				if line.startswith('feita='):
					line = line[6:].strip()
				if line:
					self.done[GuideLib.NormalizeText(line)] = line
		except Exception as e:
			GuideLib.Log('[DoneLog] load ERR: %r' % e)

	def Reload(self):
		self.Load()

	def Save(self):
		try:
			path = self._Path()
			if path is None:
				return
			d = os.path.dirname(path)
			if not os.path.isdir(d):
				os.makedirs(d)
			f = open(path, 'w')
			f.write('# MT2Guide - missoes JA FEITAS deste personagem\n')
			for key in sorted(self.done.keys()):
				f.write('feita=%s\n' % self.done[key])
			f.close()
		except Exception as e:
			GuideLib.Log('[DoneLog] save ERR: %r' % e)

	def Mark(self, name):
		if not name:
			return
		self.done[GuideLib.NormalizeText(name)] = name
		self.Save()

	def Merge(self, names):
		# junta as missoes que o JOGO disse que estao feitas
		changed = False
		for nm in (names or []):
			if not nm:
				continue
			k = GuideLib.NormalizeText(nm)
			if k and k not in self.done:
				self.done[k] = nm
				changed = True
		if changed:
			self.Save()

	def IsDone(self, name, extra=()):
		k = GuideLib.NormalizeText(name)
		if k and k in self.done:
			return True
		for e in extra:
			k = GuideLib.NormalizeText(e)
			if k and k in self.done:
				return True
		return False

	def Count(self):
		return len(self.done)


# ------------------------------------------------------------- gravador ----
# Grava os acontecimentos reais do jogo (cliques em NPC, respostas de
# dialogo, posicoes) num ficheiro no MESMO formato da base de dados ->
# editar/renomear e ja' esta' uma quest nova (aprender = gravar).
class Recorder:
	def __init__(self):
		self.active = False
		self.f = None
		self.quest_header = []
		self._pending_npc = None   # (vnum,name) a espera do dialogo
		self._lastSnap = {}        # mobs vivos vistos no ultimo scan
		self._kills = {}           # vnum -> [count, name, x, y]
		self._killPoll = 0.0

	def Start(self):
		if self.active:
			return True
		try:
			if not os.path.isdir(DATA_DIR):
				os.makedirs(DATA_DIR)
			self.f = open(RECORDED_FILE, 'a')
			self.active = True
			self._lastSnap = {}
			self._kills = {}
			self.f.write('\n# ==== gravado em (ver datas do ficheiro) ====\n')
			self.f.write('[QUEST]\nname = NOVA_%d\nmap = %s\nlevel = %d\nsteps:\n' % (
				int(GuideLib.Monotonic()), GuideLib.GetMapName(), GuideLib.GetMyLevel()))
			k = GuideLib.GetMyKingdom()
			if k:
				self.f.write('# reino do jogador: %s (posicoes das cidades 1/2 sao POR REINO;\n' % GuideLib.KINGDOM_NAMES.get(k, '?'))
				self.f.write('# junta as dos outros reinos com s:x,y;c:x,y;j:x,y)\n')
			self.f.write('# mobs mortos sao contados automaticamente (todos os mobs)\n')
			self.f.flush()
			return True
		except Exception as e:
			GuideLib.Log('[Recorder] start ERR: %r' % e)
			self.f = None
			self.active = False
			return False

	def Stop(self):
		if self.f is not None:
			try:
				self._FlushKills()
				self.f.write('# ==== fim da gravacao ====\n')
				self.f.close()
			except:
				pass
		self.f = None
		self.active = False

	# ------------------------------------------------- kills de TODOS os mobs --
	def PollKills(self):
		# chamado pela janela principal (~1x/seg): detecta mobs que
		# morreram perto de nos e conta-os (para APRENDER a quest)
		if not self.active or self.f is None:
			self._lastSnap = {}
			return
		now = GuideLib.Monotonic()
		if now - self._killPoll < 1.0:
			return
		self._killPoll = now
		snap = {}
		try:
			for (vid, t, x, y, race, name) in GuideLib.SnapshotInstances():
				if t != GuideLib.MONSTER_TYPE and t != GuideLib.METIN_TYPE:
					continue
				snap[vid] = (race, name, x, y)
		except:
			return
		try:
			px, py, pz = GuideLib.GetMyPosition()
			for vid in self._lastSnap:
				race, name, x, y = self._lastSnap[vid]
				if vid in snap:
					continue
				if GuideLib.dist(px, py, x, y) < 3000.0:
					self._OnKill(race, name, x, y)
		except:
			pass
		self._lastSnap = snap

	def _OnKill(self, race, name, x, y):
		rec = self._kills.get(race)
		if rec is None:
			rec = self._kills[race] = [0, name or '?', x, y]
			try:
				self.f.write('# MOB %s (vnum %s) visto/morto por aqui:\n' % (name or '?', race))
				self.f.flush()
			except:
				pass
		rec[0] += 1
		rec[2] = x
		rec[3] = y

	def _FlushKills(self):
		# escreve os passos kill agregados (ao parar a gravacao)
		if not self._kills:
			return
		k = GuideLib.GetMyKingdom()
		letter = GuideLib.KINGDOM_LETTERS[k] if 0 < k <= 3 else ''
		try:
			self.f.write('# --- mobs mortos nesta gravacao ---\n')
			items = sorted(self._kills.items(), key=lambda kv: -kv[1][0])
			for race, (cnt, name, x, y) in items:
				if letter:
					posfield = '%s:%.0f,%.0f' % (letter, x, y)
				else:
					posfield = '%.0f,%.0f' % (x, y)
				self.f.write('  kill | %s | %s | %d | %s | Mata %dx %s | \n' % (
					(name or '?'), race, cnt, posfield, cnt, (name or '?')))
			self.f.flush()
		except Exception as e:
			GuideLib.Log('[Recorder] flush kills ERR: %r' % e)

	def OnNpcClick(self, vid):
		if not self.active or self.f is None:
			return
		try:
			name = chr.GetNameByVID(vid) or '?'
			chr.SelectInstance(vid)
			race = chr.GetRace()
			x, y, z = eXLib.GetPixelPosition(vid)
			px, py, pz = GuideLib.GetMyPosition()
			# posicao por reino nas cidades 1/2; comum nos outros mapas
			k = GuideLib.GetMyKingdom()
			letter = GuideLib.KINGDOM_LETTERS[k] if 0 < k <= 3 else ''
			if letter:
				posfield = '%s:%.0f,%.0f' % (letter, x, y)
			else:
				posfield = '%.0f,%.0f' % (x, y)
			self.f.write('# clique NPC %s (vnum %s) a %.0f px; tu em %.0f,%.0f [%s]\n' % (
				name, race, GuideLib.dist(px, py, x, y), px, py,
				GuideLib.KINGDOM_NAMES.get(k, 'mapa comum')))
			self.f.write('  talk | %s | %s | | %s | FALA COM %s | \n' % (
				name, race, posfield, name))
			self.f.flush()
			self._pending_npc = (race, name)
		except Exception as e:
			GuideLib.Log('[Recorder] npc ERR: %r' % e)

	def OnDialogAnswer(self, answer_index, answer_value, count):
		if not self.active or self.f is None:
			return
		try:
			self.f.write('#    dialogo (opcoes=%d) -> escolheste o quadrado %s\n' % (count, answer_index))
			self.f.flush()
		except:
			pass

	def WriteNote(self, text):
		if not self.active or self.f is None:
			return
		try:
			px, py, pz = GuideLib.GetMyPosition()
			k = GuideLib.GetMyKingdom()
			letter = GuideLib.KINGDOM_LETTERS[k] if 0 < k <= 3 else ''
			if letter:
				posfield = '%s:%.0f,%.0f' % (letter, px, py)
			else:
				posfield = '%.0f,%.0f' % (px, py)
			self.f.write('  goto | | | | %s | %s | \n' % (posfield, text))
			self.f.flush()
		except:
			pass


# helpers usados pelo Recorder (chr vem do GuideLib)
try:
	chr = GuideLib.chr
except AttributeError:
	chr = None

Log = GuideLib.Log
