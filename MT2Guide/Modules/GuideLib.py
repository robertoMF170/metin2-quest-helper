# -*- coding: utf-8 -*-
# MT2Guide - GuideLib.py
# Biblioteca base do Quest Helper (auto-contida, nao depende do MT2Robs).
# Fornece: scan dos modulos do cliente, relogio monotonicico, distancias/rotacoes,
# hook de fase, gerador da seta (TGA) e utilidades uteis ao guia.
import sys
_chr = chr

try:
	import __builtin__ as buildin
except ImportError:
	import builtins as buildin

try:
	import time as _walltime
except ImportError:
	pass

def HasArguments(module, attrlist):
	for attr in attrlist:
		if not buildin.hasattr(module, attr):
			return False
	return True

# ---- scan dos modulos do cliente (mesma tecnica do MT2Robs/Hooks) ----
for modulename, module in iter(sys.modules.items()):
	if HasArguments(module, ['clock']): time = module
	if HasArguments(module, ['GetPlayTime']): player = module
	if HasArguments(module, ['GetNameByVID']): chr = module
	if HasArguments(module, ['DirectEnter']): net = module
	if HasArguments(module, ['SetCameraMaxDistance']): app = module
	if HasArguments(module, ['GetCurrentMapName']): background = module
	if HasArguments(module, ['SelectAnswer']): event = module
	if HasArguments(module, ['ScriptWindow']): ui = module
	if HasArguments(module, ['factorial']): math = module
	if HasArguments(module, ['GameWindow']): game = module
	if HasArguments(module, ['GetGradeByVID']): nonplayer = module

# o scan acima apanha o modulo math do cliente; se nao apanhar (nome
# diferente), importa o math normal -> dist/rotacao nunca rebentam
try:
	math
except NameError:
	try:
		import math
	except ImportError:
		pass

import eXLib

PHASE_LOGIN = 1
PHASE_SELECT = 2
PHASE_GAME = 5

# ---------------------------------------------------------------- logging --
def Log(text):
	try:
		from datetime import datetime
		stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		f = open(eXLib.PATH + 'syserr_guide.txt', 'a')
		f.write('[%s] %s\n' % (stamp, text))
		f.close()
	except:
		pass

# ------------------------------------------------------------ relogios ----
# O app.GetTime() corre suave mas reseta a ~0 em cada reload do mundo; o
# time.time() da maquina congela aos blocos (log comprovou no MT2Robs).
# Este relogio cose os resets e corre a velocidade do jogo.
_monot_last = [0.0]
_monot_offset = [0.0]

def Monotonic():
	try:
		t = app.GetTime()
	except:
		try:
			return _walltime.time()
		except:
			return 0.0
	if t < _monot_last[0]:
		_monot_offset[0] += _monot_last[0] - t   # reload do mundo -> continuidade
	_monot_last[0] = t
	return t + _monot_offset[0]

def GetTime():
	try:
		return app.GetTime()
	except:
		return Monotonic()

# ------------------------------------------------------------- mundo ------
def WorldSettled():
	# True quando o mundo esta REALMENTE carregado (apos o load, mexer em
	# UI/instancias pode corromper o heap -> crashes 0xc0000374).
	try:
		if not background.GetCurrentMapName():
			return False
		mVID = player.GetMainCharacterIndex()
		if not mVID:
			return False
		x, y, z = eXLib.GetPixelPosition(mVID)
		if buildin.abs(x) < 1.0 and buildin.abs(y) < 1.0:
			return False
	except:
		return False
	return True

def GetMapName():
	try:
		return background.GetCurrentMapName() or ''
	except:
		return ''

# ------------------------------------------------- caminhos da base -------
def GameRoot():
	try:
		return eXLib.PATH
	except:
		return ''

def DataDir():
	import os
	return os.path.join(GameRoot(), 'MT2Guide', 'Data')

def SavesDir():
	import os
	return os.path.join(GameRoot(), 'MT2Guide', 'Saves')

def SafeCharName():
	# nome do personagem ligado, seguro para nome de ficheiro
	name = GetMyName() or 'jogador'
	bad = '\\/:*?"<>|'
	safe = ''
	for c in name:
		if c not in bad:
			safe += c
	safe = safe.strip()
	return safe or 'jogador'

def StateFileName():
	try:
		return '%s_quests.txt' % SafeCharName()
	except:
		return 'estado_quests.txt'

# ------------------------------------------------------------- texto ------ #
# Normaliza titulos para comparar/pesquisar sem acentos nem maiusculas:
# "Investigação do Biólogo" -> "investigacao do biologo"
try:
	_TEXT_TYPE = unicode                       # cliente (python 2)
except NameError:
	_TEXT_TYPE = str                           # python 3 (testes fora do jogo)

_ACCENTS = {
	u'\xe0': 'a', u'\xe1': 'a', u'\xe2': 'a', u'\xe3': 'a', u'\xe4': 'a', u'\xe5': 'a',
	u'\xe8': 'e', u'\xe9': 'e', u'\xea': 'e', u'\xeb': 'e',
	u'\xec': 'i', u'\xed': 'i', u'\xee': 'i', u'\xef': 'i',
	u'\xf2': 'o', u'\xf3': 'o', u'\xf4': 'o', u'\xf5': 'o', u'\xf6': 'o',
	u'\xf9': 'u', u'\xfa': 'u', u'\xfb': 'u', u'\xfc': 'u',
	u'\xe7': 'c', u'\xf1': 'n', u'\xfd': 'y',
}

def NormalizeText(text):
	# devolve SEMPRE texto normalizado (unicode): minusculas, sem acentos,
	# espacos colapsados. Serve para comparar e pesquisar.
	if text is None:
		return u''
	s = text
	if not buildin.isinstance(s, _TEXT_TYPE):
		try:
			s = s.decode('utf-8', 'ignore')
		except:
			s = _TEXT_TYPE(s)
	out = []
	for ch in s:
		try:
			low = ch.lower()
		except:
			low = ch
		out.append(_ACCENTS.get(low, low))
	s = u''.join(out)
	return u' '.join(s.split())

def Contains(haystack, needle):
	# pesquisa tolerante (sem acentos/maiusculas), em qualquer direccao
	n = NormalizeText(needle)
	if not n:
		return False
	return n in NormalizeText(haystack)

# ------------------------------------------------------------- reinos ----
# As cidades 1 e 2 sao DIFERENTES por reino; os outros mapas (vale, torre,
# deserto, Sohan...) sao comuns a todos.
#   metin2_map_a1/a2 -> Shinsoo (vermelho, Yongan)
#   metin2_map_b1/b2 -> Chunjo  (amarelo,  Joan)
#   metin2_map_c1/c2 -> Jinno   (azul,    Pyungmoo)
KINGDOM_SHINSOO = 1
KINGDOM_CHUNJO = 2
KINGDOM_JINNO = 3
KINGDOM_COMMON = 0
KINGDOM_NAMES = {
	KINGDOM_SHINSOO: 'Shinsoo (vermelho)',
	KINGDOM_CHUNJO: 'Chunjo (amarelo)',
	KINGDOM_JINNO: 'Jinno (azul)',
	KINGDOM_COMMON: 'mapa comum',
}
KINGDOM_LETTERS = ('', 's', 'c', 'j')   # indice -> letra usada nos passos

def GetKingdomByMap(mapname):
	m = (mapname or '').lower()
	if m.startswith('metin2_map_a1') or m.startswith('metin2_map_a2'):
		return KINGDOM_SHINSOO
	if m.startswith('metin2_map_b1') or m.startswith('metin2_map_b2'):
		return KINGDOM_CHUNJO
	if m.startswith('metin2_map_c1') or m.startswith('metin2_map_c2'):
		return KINGDOM_JINNO
	return KINGDOM_COMMON

def GetMyKingdom():
	# reino deduzido do mapa atual (0 = mapa comum a todos os reinos)
	return GetKingdomByMap(GetMapName())

def GetMyPosition():
	try:
		vid = player.GetMainCharacterIndex()
		if not vid:
			return (0, 0, 0)
		return eXLib.GetPixelPosition(vid)
	except:
		return (0, 0, 0)

def GetMyName():
	try:
		return chr.GetNameByVID(player.GetMainCharacterIndex()) or ''
	except:
		return ''

def GetMyLevel():
	for fn in ('GetStatus', 'GetLevel'):
		try:
			f = getattr(player, fn, None)
			if f is None:
				continue
			if fn == 'GetLevel':
				return int(f())
			r = f(5)   # POINT_LEVEL
			try:
				return int(r)
			except:
				continue
		except:
			continue
	return 0

# --------------------------------------------------------- geometria ------
def dist(x1, y1, x2, y2):
	return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

def GetRotation(x0, y0, x1, y1):
	# Rotacao (graus, contexto do jogo) para (x0,y0) apontar para (x1,y1).
	x1_relative = x1 - x0
	y1_relative = y1 - y0
	try:
		rada = 180 * (math.acos(y1_relative / math.sqrt((x1_relative) ** 2 + (y1_relative) ** 2))) / math.pi + 180
		if x0 >= x1:
			rada = 360 - rada
	except:
		rada = 0
	return rada

# ---------------------------------------------------------- instancias ----
# Tipos (convencao uBot): monster=0, ore/objecto=1, metin=2, player=6.
MONSTER_TYPE = 0
OBJECT_TYPE = 1
METIN_TYPE = 2
PLAYER_TYPE = 6

def SnapshotInstances():
	# [(vid, tipo, x, y, race, nome)] vivos, no alcance do cliente.
	# IMPORTANTE (cliente TR/eXLib): GetRace() e' SEM argumento e so' da
	# o resultado DEPOIS de chr.SelectInstance(vid) -- assim faz o bot.
	snap = []
	try:
		vids = list(eXLib.InstancesList)
	except:
		return snap
	for vid in vids:
		try:
			vid = int(vid)
			if not chr.HasInstance(vid) or eXLib.IsDead(vid):
				continue
			chr.SelectInstance(vid)
			race = chr.GetRace()
			try:
				t = chr.GetInstanceType()
			except:
				try:
					t = chr.GetInstanceType(vid)
				except:
					t = 0
			x, y, z = eXLib.GetPixelPosition(vid)
			name = chr.GetNameByVID(vid)
			snap.append((vid, t, x, y, race, name))
		except:
			continue
	return snap

def FindInstancesByRace(race):
	out = []
	for (vid, t, x, y, r, name) in SnapshotInstances():
		if r == race:
			out.append((vid, x, y, name))
	return out

def FindNearestByRace(race, mx, my):
	best = None
	bestD = 1e18
	for (vid, x, y, name) in FindInstancesByRace(race):
		d = (x - mx) * (x - mx) + (y - my) * (y - my)
		if d < bestD:
			bestD = d
			best = (vid, x, y, name)
	return best

def FindInstancesByName(needle):
	# [(vid, x, y, nome)] das instancias cujo NOME (o que o cliente tem
	# para aquele vid) contem `needle`. Serve para achar os mobs das
	# MISSOES DE CACA antes de o guia saber o vnum deles.
	n = NormalizeText(needle)
	if not n or len(n) < 3:
		return []
	out = []
	for (vid, t, x, y, r, name) in SnapshotInstances():
		if not name:
			continue
		nm = NormalizeText(name)
		if not nm:
			continue
		if n in nm or nm in n:
			out.append((vid, x, y, name))
	return out

def FindNearestByName(needle, mx, my):
	best = None
	bestD = 1e18
	for (vid, x, y, name) in FindInstancesByName(needle):
		d = (x - mx) * (x - mx) + (y - my) * (y - my)
		if d < bestD:
			bestD = d
			best = (vid, x, y, name)
	return best

def TargetInstance():
	# (vid, race, nome) da instancia que o JOGADOR tem travada agora
	# (alvo do cliente). (0, 0, '') se nao ha alvo. E' por aqui que o
	# guia DESCOBRE sozinho qual das 2 opcoes o jogador escolheu.
	try:
		vid = int(player.GetTargetVID())
	except Exception:
		vid = 0
	if not vid:
		return (0, 0, '')
	try:
		if not chr.HasInstance(vid):
			return (0, 0, '')
	except Exception:
		pass
	race = 0
	try:
		chr.SelectInstance(vid)
		race = chr.GetRace()
	except Exception:
		race = 0
	name = ''
	try:
		name = chr.GetNameByVID(vid) or ''
	except Exception:
		name = ''
	return (vid, race, name)

# ------------------------------------------------------------ fase hook ---
# Mini-hook de net.SetPhaseWindow (igual ao Hooks.py do MT2Robs) para saber
# quando entramos no jogo / reload do mundo.
try:
	import functools
except ImportError:
	functools = None

_phaseCallbacks = {}
CURRENT_PHASE = [0]

def registerPhaseCallback(id, func):
	_phaseCallbacks[id] = func

def deletePhaseCallback(id):
	if id in _phaseCallbacks:
		del _phaseCallbacks[id]

	def _phaseIntercept(*args, **kwargs):
		if len(args) > 1 and args[1] != 0:
			CURRENT_PHASE[0] = args[0]
		for cid in list(_phaseCallbacks.keys()):
			cb = _phaseCallbacks.get(cid)
			if buildin.callable(cb):
				try:
					cb(CURRENT_PHASE[0], args[1] if len(args) > 1 else 0)
				except:
					pass
		# BUGFIX: _phaseHookOrig e' uma LISTA (cell) -> chamar _phaseHookOrig[0].
		# Antes crashava 'list' object is not callable em CADA mudanca de fase
		# e o net.SetPhaseWindow original nunca corria (partia as fases/teclas).
		return _phaseHookOrig[0](*args, **kwargs)

_phaseHookInstalled = [False]
_phaseHookOrig = [None]

def InstallPhaseHook():
	if _phaseHookInstalled[0]:
		return
	try:
		_phaseHookOrig[0] = net.SetPhaseWindow
		net.SetPhaseWindow = _phaseIntercept
		_phaseHookInstalled[0] = True
	except:
		pass

def GetCurrentPhase():
	return CURRENT_PHASE[0]

def IsInGamePhase():
	return GetCurrentPhase() == PHASE_GAME

# -------------------------------------------------- gerador da SETA TGA ---
# Seta amarela apontando para CIMA (32bpp uncompressed TGA, alpha).
# Escrita em Python puro: sem dependencias, gera 1x na 1a execucao.
def _WriteArrowTGA(path, size=48):
	W = H = size
	cx = W / 2.0
	buf = bytearray()
	buf.append(0); buf.append(0); buf.append(2)             # id, colormap, tipo 2
	for _i in range(9):
		buf.append(0)                                       # colormap + origem
	buf.append(W & 255); buf.append((W >> 8) & 255)         # largura
	buf.append(H & 255); buf.append((H >> 8) & 255)         # altura
	buf.append(32); buf.append(8)                           # bpp=32, topo-esquerda
	for j in range(H):
		for i in range(W):
			x = i - cx
			y = cx - j   # y cresce para cima
			inside = False
			# cabeca (triangulo)
			if y >= H * 0.45:
				lim = (y - H * 0.45) / (H * 0.55) * (W * 0.48)
				if buildin.abs(x) <= lim:
					inside = True
			# haste (retangulo)
			elif y >= H * 0.12:
				if buildin.abs(x) <= W * 0.11:
					inside = True
			if inside:
				buf.append(64); buf.append(226); buf.append(255); buf.append(255)   # BGRA amarelo
			else:
				buf.append(0); buf.append(0); buf.append(0); buf.append(0)
	try:
		f = open(path, 'wb')
		f.write(bytes(buf))
		f.close()
		return True
	except:
		return False

def ArrowImagePath():
	import os
	path = os.path.join(eXLib.PATH, 'MT2Guide', 'Data', 'arrow_up.tga')
	if not os.path.exists(path):
		try:
			os.makedirs(os.path.join(eXLib.PATH, 'MT2Guide', 'Data'))
		except:
			pass
		_WriteArrowTGA(path)
	return path

# ------------------------------------------------- gerador da MIRA TGA ----
# Mira VERMELHA (anel + cruz + ponto) que aparece POR CIMA do mob que a
# missao atual manda matar. Formato igual ao da seta (32bpp, topo-esquerda).
def _NearMask(mask, W, H, i, j):
	# o píxel vizinho faz parte da mira? (serve para o contorno preto)
	for dy in (-1, 0, 1):
		for dx in (-1, 0, 1):
			x = i + dx
			y = j + dy
			if 0 <= x < W and 0 <= y < H and mask[y * W + x]:
				return True
	return False


def _WriteMiraTGA(path, size=64):
	W = H = size
	c = (size - 1) / 2.0
	r_lo = size * 0.29
	r_hi = size * 0.375
	arm = size * 0.47
	thick = size * 0.03
	dot = size * 0.07
	mask = bytearray(W * H)
	for j in range(H):
		for i in range(W):
			dx = i - c
			dy = j - c
			d2 = dx * dx + dy * dy
			r = d2 ** 0.5
			on = False
			if r_lo <= r <= r_hi:
				on = True                                  # anel
			elif buildin.abs(dx) <= thick and r <= arm:
				on = True                                  # cruz vertical
			elif buildin.abs(dy) <= thick and r <= arm:
				on = True                                  # cruz horizontal
			elif d2 <= dot * dot:
				on = True                                  # ponto central
			if on:
				mask[j * W + i] = 1
	buf = bytearray()
	buf.append(0); buf.append(0); buf.append(2)             # id, colormap, tipo 2
	for _i in range(9):
		buf.append(0)                                       # colormap + origem
	buf.append(W & 255); buf.append((W >> 8) & 255)         # largura
	buf.append(H & 255); buf.append((H >> 8) & 255)         # altura
	buf.append(32); buf.append(8)                           # bpp=32, topo-esquerda
	for j in range(H):
		for i in range(W):
			if mask[j * W + i]:
				buf.append(0); buf.append(0); buf.append(255); buf.append(255)   # BGRA vermelho
			elif _NearMask(mask, W, H, i, j):
				buf.append(0); buf.append(0); buf.append(0); buf.append(190)     # contorno preto
			else:
				buf.append(0); buf.append(0); buf.append(0); buf.append(0)
	try:
		f = open(path, 'wb')
		f.write(bytes(buf))
		f.close()
		return True
	except:
		return False


def MiraImagePath():
	import os
	path = os.path.join(eXLib.PATH, 'MT2Guide', 'Data', 'mira_mob.tga')
	if not os.path.exists(path):
		try:
			os.makedirs(os.path.join(eXLib.PATH, 'MT2Guide', 'Data'))
		except:
			pass
		_WriteMiraTGA(path)
	return path


# ------------------------------------------- projecao 3D -> ecra ---------
# chr.GetProjectPosition(vid) devolve a posicao da instancia NO ECRA (x,y):
# e' o que permite desenhar a mira POR CIMA DO MOB (e nao no chao). A
# chamada e' sondada UMA vez e memorizada; se o cliente nao souber projetar,
# o guia continua a funcionar - so' nao desenha miras.
_projPat = [None]

def _NormProj(r):
	# aceita (x, y), (x, y, z) ou listas -> (int, int) ou None
	if r is None:
		return None
	try:
		n = len(r)
	except:
		return None
	if n < 2:
		return None
	try:
		x = float(r[0])
		y = float(r[1])
	except:
		return None
	if x != x or y != y:
		return None                       # NaN
	if buildin.abs(x) > 20000.0 or buildin.abs(y) > 20000.0:
		return None
	return (int(x), int(y))

def ProjectToScreen(vid):
	# (x, y) no ecra ou None (sem projecao / instancia invisivel)
	if _projPat[0] == -1:
		return None
	try:
		vid = int(vid)
	except:
		return None
	if _projPat[0] is not None:
		try:
			if _projPat[0] == 0:
				return _NormProj(chr.GetProjectPosition(vid))
			if _projPat[0] == 1:
				return _NormProj(chr.GetProjectPosition(vid, 0))
			return _NormProj(eXLib.GetProjectPosition(vid))
		except:
			return None
	pats = ((0, lambda v: chr.GetProjectPosition(v)),
	        (1, lambda v: chr.GetProjectPosition(v, 0)),
	        (2, lambda v: eXLib.GetProjectPosition(v)))
	for idx, fn in pats:
		try:
			r = _NormProj(fn(vid))
		except Exception as e:
			Log('[projecao] padrao %d falhou: %r' % (idx, e))
			continue
		if r is None:
			continue
		_projPat[0] = idx
		Log('[projecao] posicao no ecra OK (padrao %d) -> %r' % (idx, r))
		return r
	_projPat[0] = -1
	Log('[projecao] este cliente nao tem projecao por instancia (miras OFF)')
	return None


# ----------------------------------------------------------- skins/botoes -
BTN_BIG = ('d:/ymir work/ui/public/large_button_01.sub',
           'd:/ymir work/ui/public/large_button_02.sub',
           'd:/ymir work/ui/public/large_button_03.sub')
BTN_SML = ('d:/ymir work/ui/public/small_button_01.sub',
           'd:/ymir work/ui/public/small_button_02.sub',
           'd:/ymir work/ui/public/small_button_03.sub')

# Efeito compasso 3D do cliente (o mesmo do StoneCompass).
COMPASS_EFFECTS = {
	'Small':  "d:/ymir work/effect/etc/compass/appear_small.mse",
	'Medium': "d:/ymir work/effect/etc/compass/appear_middle.mse",
	'Large':  "d:/ymir work/effect/etc/compass/appear_large.mse",
}
DEFAULT_COMPASS = COMPASS_EFFECTS['Medium']

# ------------------------------------------------ efeito em posicao -------
# CreateEffect do eXLib (o MESMO que o MT2Robs usa para o anel da zona de
# hunt - "pattern 0 works" nos logs). O padrao de argumentos e' sondado
# UMA vez e memorizado. Serve para o SIMBOLO luminoso por cima do mob.
MARK_EFFECT = "d:/ymir work/effect/etc/compass/appear_small.mse"
_cePat = [None]

def CreateEffectAt(fx, x, y, z):
	try:
		if _cePat[0] is None:
			for i, pat in enumerate(((fx, int(x), int(y), z), (int(x), int(y), z, fx), (fx, int(x), int(y), z, 0.0))):
				try:
					eXLib.CreateEffect(*pat)
					_cePat[0] = i
					Log('[efeito] CreateEffect padrao %d OK' % i)
					return True
				except TypeError:
					continue
				except Exception as e:
					Log('[efeito] CreateEffect pat%d ERR: %r' % (i, e))
			_cePat[0] = -1
			Log('[efeito] CreateEffect indisponivel neste cliente')
			return False
		if _cePat[0] < 0:
			return False
		if _cePat[0] == 0:
			eXLib.CreateEffect(fx, int(x), int(y), z)
		elif _cePat[0] == 1:
			eXLib.CreateEffect(int(x), int(y), z, fx)
		else:
			eXLib.CreateEffect(fx, int(x), int(y), z, 0.0)
		return True
	except:
		return False

def MarkMob(x, y, z):
	# simbolo luminoso na posicao do mob-alvo (nasce no chao, onde o mob
	# esta' - atualizado de 2 em 2 segundos segue os mobs vivos)
	try:
		return CreateEffectAt(MARK_EFFECT, x, y, z)
	except:
		return False

def RGB(r, g, b):
	# escala do SetFontColor do cliente (canal cheio = 255*255)
	return (r * 255, g * 255, b * 255)

COL_STEP_DONE = RGB(120, 120, 120)
COL_STEP_CUR  = RGB(255, 216, 0)
COL_STEP_TODO = RGB(200, 200, 200)
COL_HINT      = RGB(0, 255, 128)
COL_INFO      = RGB(255, 255, 255)
COL_DIST      = RGB(120, 200, 255)
COL_MIRA_TEXT = RGB(255, 235, 140)   # etiqueta do mob com a MIRA

# ---- patch do ui.ComboBox (o mesmo do UIComponents; necessario para
# GetCurrentText/GetSelectedIndex funcionarem no nosso combo) ----
def _ComboGetCurrentText(self):
	return self.textLine.GetText()

def _ComboGetSelectedIndex(self):
	try:
		return self.listBox.GetSelectedItem()
	except:
		return -1

def _ComboOnSelectItem(self, index, name):
	self.SetCurrentItem(name)
	self.CloseListBox()
	try:
		self.event()
	except:
		pass

try:
	if buildin.hasattr(ui, 'ComboBox'):
		ui.ComboBox.GetCurrentText = _ComboGetCurrentText
		ui.ComboBox.GetSelectedIndex = _ComboGetSelectedIndex
		ui.ComboBox.OnSelectItem = _ComboOnSelectItem
except:
	pass

Log('[GuideLib] carregado')
