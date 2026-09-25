# -*- coding: utf-8 -*-
# MT2Guide - GuideUI.py
# Janela principal do Quest Helper (estilo RestedXP):
#   - escolher a quest/linha de missoes
#   - lista de passos (verde = feito, amarelo = atual, cinza = futuro)
#   - seta + distancia (HUD) e apontador 3D para onde ir
#   - dica de DIALOGO: que quadrado escolher ao falar com o NPC
#   - botao N: abre a janela de missoes do jogo
#   - gravador: aprende os passos enquanto jogas (como as rotas do Energy)
# APENAS GUIA: nada de auto-ataque, auto-andar, auto-resposta. Tu jogas,
# o guia aponta.
import sys

try:
	import __builtin__ as buildin
except ImportError:
	import builtins as buildin

import GuideLib
import GuideData
import GuideDialog
import GuideMark
import GuideQuestSync
import eXLib

player = GuideLib.player
chr = GuideLib.chr
app = GuideLib.app
ui = GuideLib.ui

TICK = 0.25          # seg entre actualizacoes do motor
LIST_VER = [0]       # versionador da lista de passos

# --- MIRA VERMELHA por cima dos mobs que a missao manda matar ---
MIRA_RANGE = 9000.0  # px: so' marca mobs razoavelmente perto do jogador
MIRA_MAX = 12        # maximo de miras ao mesmo tempo (a mais proxima 1o)
KILL_RANGE = 4500.0  # px: morte mais longe que isto nao conta

# ------------------------------------------------ estado REAL da missao --- #
STATE_DONE = 'feita'         # ja' feita (o guia ou o JOGO dizem que sim)
STATE_ACTIVE = 'ativa'       # a meio (esta' no log de missoes do jogo)
STATE_TODO = 'porfazer'      # ainda nao comecou

STATE_TAG = {STATE_DONE: '[x]', STATE_ACTIVE: '[>]', STATE_TODO: '[ ]'}
STATE_COLOR = {
	STATE_DONE: GuideLib.COL_STEP_DONE,
	STATE_ACTIVE: GuideLib.COL_STEP_CUR,
	STATE_TODO: GuideLib.COL_STEP_TODO,
}

AUTO_FOLLOW_LOCK = 25.0   # seg em que a escolha manual ganha ao jogo
AUTO_JUMP_MAX = 3        # maximo de saltos automaticos por minuto


def _StepListItemClass():
	class ListItem(ui.ListBoxEx.Item):
		def __init__(self, text, color):
			ui.ListBoxEx.Item.__init__(self)
			self.textLine = ui.TextLine()
			self.textLine.SetParent(self)
			self.textLine.SetPosition(0, 0)
			try:
				self.textLine.SetFontColor(color[0], color[1], color[2])
			except:
				pass
			self.textLine.SetText(text)
			self.textLine.SetOutline()
			self.textLine.Show()

		def __del__(self):
			ui.ListBoxEx.Item.__del__(self)

		def SetSize(self, width, height):
			ui.ListBoxEx.Item.SetSize(self, 6 * len(self.textLine.GetText()) + 4, height)
	return ListItem


def _QuestLabel(q, state=None, limit=56):
	# etiqueta da quest na quest line:
	#   [x]/[>]/[ ]  = estado REAL (feita / a meio / por fazer)
	#   [Principal]  = tipo da missao (o filtro do jogo)
	#   Lv.. + titulo PT (senao EN) + subtitulo real do jogo, quando existe
	base = getattr(q, 'name_pt', '') or q.name
	if q.name.startswith('[P]'):
		base = q.name
	head = ''
	if state:
		head += STATE_TAG.get(state, '') + ' '
	try:
		head += '[%s] ' % q.KindLabel()
	except:
		pass
	if q.level:
		head += 'Lv%d ' % q.level
	lab = head + base
	sub = getattr(q, 'subtitle', '') or getattr(q, 'chapter', '')
	if sub and GuideLib.NormalizeText(sub) != GuideLib.NormalizeText(base):
		lab += '  ' + sub
	if limit and len(lab) > limit:
		lab = lab[:limit - 3] + '...'
	return lab


def _MatchQuest(q, needle):
	# pesquisa TOLERANTE (sem acentos/maiusculas) por NOME ou SUBTITULO:
	# procura no nome, no nome PT, no subtitulo REAL do jogo, no giver e no
	# texto de TODOS os passos. Varias palavras = todas tem de aparecer.
	words = GuideLib.NormalizeText(needle).split(' ')
	if not words:
		return True
	try:
		hay = GuideLib.NormalizeText(q.SearchText())
	except:
		hay = GuideLib.NormalizeText('%s %s %s' % (
			getattr(q, 'name', ''), getattr(q, 'name_pt', ''),
			getattr(q, 'subtitle', '')))
	for w in words:
		if w and w not in hay:
			return False
	return True


# pesquisa SEM caixa de texto: as teclas chegam pelo hook do eXLib
# (init_guide.py chama search_key) e nunca tocam o IME do cliente.
# O modo pesquisa TEM de estar ARMADO antes de escrever, senao as teclas
# vao para o jogo (e abrem os atalhos do jogo). Arma-se com:
#   - clicar na linha "Pesquisar:" da janela principal (ou no botao
#     "Pesquisar")
#   - abrir a quest line (tecla N / botao Missoes)
#   - comando de chat:  .qp <texto>   (funciona SEMPRE, sem usar teclas)
SEARCH = {'on': False, 'text': ''}


def search_armed():
	# o modo pesquisa esta' ativo? Se o estado se perder (ex.: a quest
	# line foi reaberta), a quest line visivel volta a armar -> a escrita
	# nunca fica muda.
	if SEARCH['on']:
		return True
	try:
		if instance.picker.IsShow():
			SEARCH['on'] = True
			return True
	except Exception:
		pass
	return False


def arm_search(text=None, showPicker=True):
	# ARMA a escrita na pesquisa: a partir daqui TODAS as teclas de texto
	# passam a alimentar a pesquisa (e nao o jogo -> os atalhos do jogo
	# nao abrem quando escreves o nome da missao).
	SEARCH['on'] = True
	if text is not None:
		SEARCH['text'] = (text or '')[:30]
	try:
		if showPicker and not instance.picker.IsShow():
			instance.ReloadDone()
			instance.picker.SetQuests(instance.quests)
			instance.picker.Open()
	except Exception:
		pass
	try:
		instance.picker.OnSearchText()
	except Exception:
		pass
	try:
		instance.sLabel.SetText('Pesquisar(*):')
		instance.info.SetText('A ESCREVER NA PESQUISA: nome da missao (ENTER = abrir a 1a, ESC = sair)')
	except Exception:
		pass
	return True


def set_search_text(text):
	# usado pelo comando de chat .qp -> pesquisa sem tocar no teclado
	arm_search(text or '')
	try:
		if not instance.picker.IsShow():
			instance.picker.Open()
		instance.picker.Refresh()
	except Exception:
		pass
	return True


# --- DIK (scancode do teclado QWERTY) -> caracter -------------------------
# As letras NAO sao sequenciais no DIK: QWERTY fica 0x10-0x19 (q..p),
# 0x1E-0x26 (a..l) e 0x2C-0x32 (z..m). Antes o mapa assumia 0x1E..0x2C = a..z
# (errado): escrever "biolog" na pesquisa dava letras trocadas e a maioria
# das teclas nao era consumida -> caiam para o jogo e abriam os atalhos.
_DIK_LETTERS = (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19,
                0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
                0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32)
_DIK_LETTER_CH = 'qwertyuiopasdfghjklzxcvbnm'


def _dik_char(key):
	# DIK -> caracter (minusculo; a pesquisa nao distingue maiusculas)
	# ATENCAO: aqui NAO se pode usar chr()/ord() sozinhos - neste modulo
	# o nome "chr" e' o MODULO chr do cliente (chr = GuideLib.chr) e a
	# chamada rebentava (TypeError) -> as teclas de letra caiam para o
	# jogo e abriam os atalhos. Usa-se o builtin explicito (buildin).
	try:
		return _DIK_LETTER_CH[_DIK_LETTERS.index(key)]
	except ValueError:
		pass
	except Exception:
		pass
	if 0x02 <= key <= 0x0B:                     # 1..0
		return buildin.chr(buildin.ord('1') + key - 0x02)
	if key == 0x39:
		return ' '                             # espaco
	if key == 0x33:
		return ','
	if key == 0x34:
		return '.'
	if key == 0x0C:
		return '-'
	return None


def search_key(key):
	# chamado pelo hook de teclas; devolve True se a tecla foi consumida
	# pela pesquisa (modo pesquisa ARMADO: ver arm_search/search_armed)
	if not search_armed():
		return False
	t = SEARCH['text']
	if key == 0x0E:                     # backspace
		SEARCH['text'] = t[:-1]
	elif key == 0x01:                   # ESC -> sair da pesquisa
		try:
			instance.picker.Close()
		except Exception:
			SEARCH['on'] = False
		try:
			instance.sLabel.SetText('Pesquisar:')
		except Exception:
			pass
		return True
	elif key == 0x1C:                   # ENTER -> abrir a 1a missao da lista
		try:
			if instance.picker.view:
				instance.picker.Choose(instance.picker.view[0])
				return True
		except Exception:
			pass
		return True
	else:
		c = _dik_char(key)
		if c is None:
			return False                # tecla nao-texto passa ao jogo
		if len(t) < 30:
			SEARCH['text'] = t + c
	# a quest line tem de estar a vista (senao escrevias 'a' escuras)
	try:
		if not instance.picker.IsShow():
			instance.picker.Open()
	except Exception:
		pass
	try:
		instance.picker.OnSearchText()
	except Exception:
		pass
	return True


class QuestPicker(ui.ScriptWindow):
	# SELETOR DE QUESTS (quest line) - abre/fecha com a tecla N ou botao
	# "Missoes". Janela flutuante na camada TOP_MOST: fica POR CIMA da
	# janela do guia e dos steps (nunca fica por baixo). Lista todas as
	# quests livres (wiki) + premium [P], com filtros de nivel e scroll.

	# --- filtros de NIVEL (linha 1) ---
	LEVEL_FILTERS = (
		('Todas', 0, 999),
		('1-40', 1, 40),
		('41-75', 41, 75),
		('76-105', 76, 105),
		('106+', 106, 999),
		('Prem', -1, -1),
	)
	# --- filtros de TIPO = "os filtros do jogo" (linha 2) ---
	TYPE_FILTERS = (
		('Todos', ''),
		('Princ', GuideData.TYPE_PRINCIPAL),
		('Secun', GuideData.TYPE_SECUNDARIA),
		('Caca', GuideData.TYPE_CACA),
		('Bio', GuideData.TYPE_BIOLOGO),
		('Cavalo', GuideData.TYPE_CAVALO),
		('Yohara', GuideData.TYPE_YOHARA),
	)
	# --- filtros de ESTADO real (linha 3) ---
	STATE_FILTERS = (
		('Todas', ''),
		('A fazer', STATE_TODO),
		('Em curso', STATE_ACTIVE),
		('Feitas', STATE_DONE),
	)

	def __init__(self, onPick, owner=None):
		ui.ScriptWindow.__init__(self)
		self.onPick = onPick
		self.owner = owner          # janela principal (estado real das quests)
		self.quests = []
		self.view = []
		self.levelIdx = 0
		self.typeIdx = 0
		self.stateIdx = 0
		self.lastPoll = 0.0
		self.ItemCls = _StepListItemClass()
		self.comp = _MiniComp()
		self._Build()
		self.Show()   # ScriptWindow visivel para o OnUpdate existir
		self.Board.Hide()

	def _Build(self):
		try:
			self.Board = ui.BoardWithTitleBar(layer='TOP_MOST')
		except:
			self.Board = ui.BoardWithTitleBar()
		self.Board.SetTitleName('MT2Guide - Quest Line (N abre/fecha)')
		self.Board.SetCloseEvent(self.Close)
		self.Board.SetSize(434, 508)
		self.Board.SetCenterPosition()
		self.Board.AddFlag('float')
		self.Board.AddFlag('movable')

		# --- linha 1: filtros de NIVEL ---
		x = 12
		self.levelBtns = []
		for i in range(len(self.LEVEL_FILTERS)):
			lab = self.LEVEL_FILTERS[i][0]
			b = self.comp.Button(self.Board, lab, 'Nivel: %s' % lab, x, 30,
			                     (lambda i=i: self.OnLevelFilter(i)), *GuideLib.BTN_SML)
			x += 62
			self.levelBtns.append(b)

		# --- linha 2: filtros de TIPO (principal/secundaria/caca/...) ---
		x = 12
		self.typeBtns = []
		for i in range(len(self.TYPE_FILTERS)):
			lab, t = self.TYPE_FILTERS[i]
			if t == GuideData.TYPE_CACA:
				tip = 'Caca: missoes com objetivos de matar/apanhar'
			else:
				tip = 'Tipo: %s' % (GuideData.TypeLabel(t) if t else 'todos os tipos')
			b = self.comp.Button(self.Board, lab, tip, x, 52,
			                     (lambda i=i: self.OnTypeFilter(i)), *GuideLib.BTN_SML)
			x += 60
			self.typeBtns.append(b)

		# --- linha 3: ESTADO real da missao (feitas / a meio / por fazer) ---
		x = 12
		self.stateBtns = []
		for i in range(len(self.STATE_FILTERS)):
			lab, s = self.STATE_FILTERS[i]
			b = self.comp.Button(self.Board, lab, 'Estado: %s' % lab, x, 74,
			                     (lambda i=i: self.OnStateFilter(i)), *GuideLib.BTN_SML)
			x += 68
			self.stateBtns.append(b)
		self.sInfo = self.comp.Text(self.Board, '', 296, 78, GuideLib.COL_INFO)

		# --- pesquisa por titulo (PT ou EN) OU SUBTITULO/objetivo: escreve
		# DIRETAMENTE com o teclado (hook do eXLib, sem caixa de texto/IME) ---
		self.sLabel = self.comp.Text(self.Board, 'Pesq:', 12, 96, GuideLib.COL_INFO)
		self.sText = self.comp.Text(self.Board, '', 50, 96, GuideLib.COL_STEP_CUR)
		self.fText = self.comp.Text(self.Board, '', 280, 96, GuideLib.COL_HINT)

		# --- lista (por cima de tudo: TOP_MOST + float) ---
		self.bar, self.listBox, self.scroll = self.comp.ListBoxEx(self.Board, 12, 116, 384, 336)
		self.listBox.SetViewItemCount(17)
		try:
			self.listBox.SetSelectEvent(self._OnPickItem)
		except:
			pass

		# --- selecionar com duplo-clique no evento acima falhar ---
		self.okBtn = self.comp.Button(self.Board, 'Seguir', 'Seguir a missao selecionada', 12, 462, self.OnFollow, *GuideLib.BTN_SML)
		self.closeBtn = self.comp.Button(self.Board, 'Fechar', 'Fechar (N)', 124, 462, self.Close, *GuideLib.BTN_SML)
		self.info = self.comp.Text(self.Board, 'pesquisa por titulo, subtitulo ou objetivo', 180, 466, GuideLib.COL_DIST)

	# ----------------------------------------------------------- lista ----
	def SetQuests(self, quests):
		self.quests = quests
		self.Refresh()

	def OnSearchText(self):
		# texto de pesquisa mudou (escrito via hook de teclas / botao)
		try:
			self.sText.SetText('> %s_' % SEARCH['text'])
			try:
				instance.qSearch.SetText(SEARCH['text'])
				instance.sLabel.SetText('Pesquisar(*):' if SEARCH['on'] else 'Pesquisar:')
			except Exception:
				pass
		except Exception:
			pass
		self.Refresh()

	def Refresh(self):
		try:
			self.listBox.RemoveAllItems()
		except:
			pass
		name, lo, hi = self.LEVEL_FILTERS[self.levelIdx]
		tname, ttype = self.TYPE_FILTERS[self.typeIdx]
		sname, sstate = self.STATE_FILTERS[self.stateIdx]
		needle = SEARCH['text']
		self.view = []
		counts = {STATE_DONE: 0, STATE_ACTIVE: 0, STATE_TODO: 0}
		for q in self.quests:
			# --- nivel ---
			if name == 'Prem':
				if not q.name.startswith('[P]'):
					continue
			elif q.level < lo or q.level > hi:
				continue
			# --- tipo (missao principal/secundaria/caca/... do JOGO) ---
			if ttype:
				hit = (q.type == ttype)
				if not hit:
					for st in q.steps:
						if st.cat == ttype:
							hit = True
							break
				# "Caca" e' transversal: mostra as missoes que obrigam a
				# matar/apanhar (kill/collect), seja qual for o tipo delas
				if not hit and ttype == GuideData.TYPE_CACA:
					for st in q.steps:
						if st.type in ('kill', 'collect'):
							hit = True
							break
				if not hit:
					continue
			# --- estado REAL (o que o guia sabe + o que o JOGO diz) ---
			state = self.StateOf(q)
			if sstate and state != sstate:
				continue
			# --- pesquisa por nome OU subtitulo/objetivo ---
			if needle and not _MatchQuest(q, needle):
				continue
			self.view.append(q)
			counts[state] = counts.get(state, 0) + 1
		# ordem do jogo: por nivel, depois por nome
		pairs = []
		for q in self.view:
			pairs.append(((q.level or 0), q.name, q))
		pairs.sort()
		self.view = [p[2] for p in pairs]
		for q in self.view:
			try:
				state = self.StateOf(q)
				self.listBox.AppendItem(self.ItemCls(_QuestLabel(q, state),
				                                     STATE_COLOR.get(state, GuideLib.COL_STEP_TODO)))
			except:
				pass
		# contadores: total | feitas | a meio | por fazer
		try:
			k = GuideLib.GetMyKingdom()
			self.fText.SetText('%d/%d | %s' % (
				len(self.view), len(self.quests),
				GuideLib.KINGDOM_NAMES.get(k, '?').split(' ')[0]))
		except:
			self.fText.SetText('%d/%d' % (len(self.view), len(self.quests)))
		try:
			self.sInfo.SetText('[x]%d [>]%d [ ]%d' % (
				counts.get(STATE_DONE, 0), counts.get(STATE_ACTIVE, 0),
				counts.get(STATE_TODO, 0)))
		except:
			pass

	def StateOf(self, q):
		# estado real da missao (pedido a' janela principal; fallback: por fazer)
		try:
			if self.owner is not None:
				return self.owner.QuestStateOf(q)
		except:
			pass
		return STATE_TODO

	def OnLevelFilter(self, idx):
		self.levelIdx = idx
		self.Refresh()

	def OnTypeFilter(self, idx):
		self.typeIdx = idx
		self.Refresh()

	def OnStateFilter(self, idx):
		self.stateIdx = idx
		self.Refresh()

	# -------------------------------------------------------- escolha ----
	def _OnPickItem(self, *args):
		if not args:
			return
		a = args[0]
		q = None
		try:
			i = int(a)
			if 0 <= i < len(self.view):
				q = self.view[i]
		except:
			pass
		if q is None:
			# candidatos a etiqueta: o proprio arg e os restantes args
			for cand in args:
				label = None
				if buildin.hasattr(cand, 'textLine'):
					try:
						label = cand.textLine.GetText()
					except:
						pass
				elif buildin.hasattr(cand, 'strip'):
					label = cand
				if not label:
					continue
				for qq in self.view:
					if _QuestLabel(qq, self.StateOf(qq)) == label or qq.name == label:
						q = qq
						break
				if q is not None:
					break
		if q is not None:
			self.Choose(q)

	def OnFollow(self):
		# plano B: usar o item selecionado da lista
		try:
			i = self.listBox.GetSelectedItem()
		except:
			i = -1
		try:
			if i is None:
				i = -1
			i = int(i)
		except:
			i = -1
		if 0 <= i < len(self.view):
			self.Choose(self.view[i])
		else:
			self.info.SetText('clica primeiro numa missao da lista')

	def Choose(self, q):
		try:
			self.Close()
			self.onPick(q)
		except:
			pass

	# -------------------------------------------------------- janela -----
	def Open(self):
		# abrir a quest line ARMA a escrita na pesquisa (as teclas de
		# texto passam a filtrar a lista em vez de irem para o jogo)
		SEARCH['on'] = True
		self.OnSearchText()
		self.Refresh()
		self.Board.Show()

	def Close(self):
		SEARCH['on'] = False
		SEARCH['text'] = ''
		try:
			self.sText.SetText('escreve o nome ou usa os filtros')
			instance.qSearch.SetText('')
			instance.sLabel.SetText('Pesquisar:')
		except:
			pass
		self.Board.Hide()

	def IsShow(self):
		try:
			return self.Board.IsShow()
		except:
			return False

	def Toggle(self):
		if self.IsShow():
			self.Close()
		else:
			self.Open()


class QuestHelperWindow(ui.ScriptWindow):

	def __init__(self):
		ui.ScriptWindow.__init__(self)
		self.comp = _MiniComp()
		self.quests = GuideData.LoadAllQuests()
		self.progress = GuideData.Progress()
		self.recorder = GuideData.Recorder()
		self.lastTick = 0.0
		self.questIdx = -1
		self._waitingDialogForVnum = 0   # talk/turnin a espera de resposta
		self._talkArmed = False
		self._talkTime = 0.0
		self._autoShown = False
		self._seenMobs = {}      # vids vivos do alvo kill (auto-contagem)
		self._killStepKey = None
		self._lastTargetLock = 0.0   # ultimo lock do alvo (simbolo no mob)
		self._lastMarkVid = None     # vid do mob ja' travado (seta vermelha)
		self._lastRearm = 0.0        # ultima reinstalacao da ponte de teclas
		self._killLogTime = 0.0      # throttle do log de vigilancia
		self.ListItemCls = _StepListItemClass()

		# --- dados REAIS da conta/personagem ligada ---
		self.sync = GuideQuestSync.instance
		self.doneLog = GuideData.DoneLog()
		self.autoFollow = True       # segue a missao em curso NO JOGO
		self._manualAt = 0.0         # ultima escolha manual (ganha ao jogo)
		self._lastJump = 0.0         # ultimo salto automatico de missao
		self._jumps = []             # saltos no ultimo minuto (anti-loop)
		self._lastCounterSync = 0.0  # ultima sincronizacao de contadores
		self._lastStateText = ''
		self._lastGameSig = ''       # assinatura das missoes ativas no jogo
		self._scanKey = None         # cache de instancias (1 varredura por tick)
		self._scanCache = {}
		self._nameCache = {}         # cache de instancias por NOME (caca sem vnum)
		self._charNow = ''           # personagem do progresso carregado
		self._stepVnums = ()         # mobs aceites pelo passo atual
		self._miraOn = True          # miras ligadas (botao Mira)
		self._autoChoiceTick = 0.0    # ultima tentativa de descobrir a opcao (caca)
		self._optSig = None          # assinatura dos botoes Op.1/Op.2

		self._BuildWindow()
		self._BindEvents()
		self._RestoreProgress()
		self._SyncStart()

		self.Show()   # ScriptWindow visivel -> OnUpdate corre

	# ----------------------------------------------------------- janela ----
	def _BuildWindow(self):
		self.Board = ui.BoardWithTitleBar()
		self.Board.SetTitleName('MT2Guide - Quest Helper')
		self.Board.SetCloseEvent(self.Close)
		self.Board.SetSize(400, 556)
		self.Board.SetCenterPosition()
		self.Board.AddFlag('movable')
		self.Board.AddFlag('float')

		import GuideNav
		self.hud = GuideNav.hud
		self.marker = GuideMark.marker
		self.dialogAdvisor = GuideDialog.advisor

		# --- linha de quests (seletor completo abre com N) ---
		self.lQuest = self.comp.Text(self.Board, 'Missao:', 12, 32, GuideLib.COL_INFO)
		self.qText = self.comp.Text(self.Board, '(nenhuma)', 68, 32, GuideLib.COL_STEP_CUR)

		# --- pesquisa por titulo (PT ou EN): SEM caixa de texto! escreve
		# diretamente com o teclado (as teclas vem pelo hook do eXLib,
		# o IME nunca fica com o foco -> INSERT/N nunca morrem) ---
		self.sLabel = self.comp.Text(self.Board, 'Pesquisar:', 12, 56, GuideLib.COL_INFO)
		self.qSearch = self.comp.Text(self.Board, '', 92, 56, GuideLib.COL_STEP_CUR)
		self.pickBtn = self.comp.Button(self.Board, 'Missoes', 'Abrir a quest line com TODAS as missoes (tecla N) e escreve para pesquisar', 300, 51, self.OnOpenQuestPicker, *GuideLib.BTN_SML)
		self.picker = QuestPicker(self.OnQuestChosen, self)

		# --- AREA CLICAVEL por cima da linha "Pesquisar:": clicar aqui
		# ARMA a escrita (o cliente nao tem caixa de texto propria, as
		# teclas vem pelo hook; sem armar, as teclas vao para o jogo e
		# abrem os atalhos do jogo) ---
		self.searchHit = None
		try:
			self.searchHit = ui.Window()
			self.searchHit.SetParent(self.Board)
			self.searchHit.SetPosition(8, 50)
			self.searchHit.SetSize(280, 20)
			self.searchHit.SetEvent(self.OnArmSearch)
			self.searchHit.Show()
		except Exception as e:
			GuideLib.Log('[GuideUI] area de pesquisa clicavel indisponivel: %r' % e)
			self.searchHit = None

		# --- lista de passos ---
		self.bar, self.listBox, self.scroll = self.comp.ListBoxEx(self.Board, 12, 78, 365, 196)
		self.listBox.SetViewItemCount(11)

		# --- detalhe do passo atual ---
		self.dTitle = self.comp.Text(self.Board, 'Passo atual:', 12, 284, GuideLib.COL_STEP_CUR)
		self.dText1 = self.comp.Text(self.Board, '', 12, 300, GuideLib.COL_INFO)
		self.dText2 = self.comp.Text(self.Board, '', 12, 314, GuideLib.COL_INFO)
		self.dHint = self.comp.Text(self.Board, '', 12, 328, GuideLib.COL_HINT)
		self.dState = self.comp.Text(self.Board, '', 12, 342, GuideLib.COL_DIST)

		# --- botoes linha 1 (mais separados) ---
		self.prevBtn = self.comp.Button(self.Board, '<', 'Passo anterior', 12, 358, self.OnPrev, *GuideLib.BTN_SML)
		self.nextBtn = self.comp.Button(self.Board, '>', 'Proximo passo', 54, 358, self.OnNext, *GuideLib.BTN_SML)
		self.killBtn = self.comp.Button(self.Board, '+1', 'Contar 1 morte/item', 96, 358, self.OnKillPlus, *GuideLib.BTN_SML)
		self.pingBtn = self.comp.Button(self.Board, 'Ping', 'Apontar 3D agora', 146, 358, self.OnPing, *GuideLib.BTN_SML)
		self.nBtn = self.comp.Button(self.Board, 'N', 'Abrir a quest line com todas as missoes', 218, 358, self.OnOpenQuestWindow, *GuideLib.BTN_SML)
		self.markerBtn = self.comp.Button(self.Board, 'Marc:ON', 'Apontador 3D on/off', 262, 358, self.OnToggleMarker, *GuideLib.BTN_SML)

		# --- botoes linha 2 (mais separados) ---
		self.trailBtn = self.comp.Button(self.Board, 'Rasto:OFF', 'Linha de pontos no chao + area de spawn (kill) - EXPERIMENTAL', 12, 390, self.OnToggleTrail, *GuideLib.BTN_SML)
		self.hudBtn = self.comp.Button(self.Board, 'HUD:ON', 'Mostrar/esconder a seta', 125, 390, self.OnToggleHud, *GuideLib.BTN_SML)
		self.recBtn = self.comp.Button(self.Board, 'Gravar:OFF', 'Gravar passos novos enquanto jogas', 210, 390, self.OnToggleRecord, *GuideLib.BTN_SML)
		self.reloadBtn = self.comp.Button(self.Board, 'Recarregar', 'Reler a base de dados de quests', 312, 390, self.OnReloadData, *GuideLib.BTN_SML)

		# --- botoes linha 3: dados REAIS do jogo ---
		self.autoBtn = self.comp.Button(self.Board, 'Segue:ON', 'Seguir automaticamente a missao em curso no JOGO (e saltar para ela)', 12, 422, self.OnToggleAutoFollow, *GuideLib.BTN_SML)
		self.doneBtn = self.comp.Button(self.Board, 'Concluir', 'Marcar esta missao como FEITA (fica [x] e sai do filtro "A fazer")', 120, 422, self.OnMarkDone, *GuideLib.BTN_SML)
		self.stateBtn = self.comp.Button(self.Board, 'Estado', 'Mostrar no log o estado real das quests do jogo (.qdump)', 228, 422, self.OnDumpState, *GuideLib.BTN_SML)
		self.followBtn = self.comp.Button(self.Board, 'Ir', 'Saltar AGORA para a missao em curso no jogo', 330, 422, self.OnFollowGame, *GuideLib.BTN_SML)

		# --- botoes linha 4: a MIRA nos mobs que a missao manda matar ---
		self.miraBtn = self.comp.Button(self.Board, 'Mira:ON', 'Mira vermelha por cima dos mobs que contam para este passo', 12, 454, self.OnToggleMira, *GuideLib.BTN_SML)
		self.searchBtn = self.comp.Button(self.Board, 'Pesquisar', 'Clique e escreva o nome da missao (procurar por nome/subtitulo/objetivo)', 262, 454, self.OnArmSearch, *GuideLib.BTN_SML)
		self.mobBtn = self.comp.Button(self.Board, 'Mobs', 'Mostrar no log os mobs do passo (vnum + quantos a vista)', 96, 454, self.OnDumpMobs, *GuideLib.BTN_SML)

		# --- botoes linha 5: MISSOES DE CACA (escolhe 1 de 2) ---
		# Op.1 / Op.2 = "escolhi a opcao 1/2 da missao" (o guia passa a
		# contar so' esse mob e a apontar-lhe a mira)
		self.op1Btn = self.comp.Button(self.Board, 'Op.1', 'Missao de caca: escolhi a OPCAO 1 (ver a linha do passo)', 12, 486, self.OnPickOpt1, *GuideLib.BTN_SML)
		self.op2Btn = self.comp.Button(self.Board, 'Op.2', 'Missao de caca: escolhi a OPCAO 2 (ver a linha do passo)', 54, 486, self.OnPickOpt2, *GuideLib.BTN_SML)
		self.chooseBtn = self.comp.Button(self.Board, 'Escolher', 'Fixar o mob que tenho ao pe' + '/como alvo (aprende o vnum dele)', 96, 486, self.OnChooseMob, *GuideLib.BTN_SML)

		# --- estado ---
		self.info = self.comp.Text(self.Board, 'pronto', 12, 518, GuideLib.COL_DIST)

		self.Board.Hide()

	# ------------------------------------------------------- eventos -------
	def _BindEvents(self):
		# cliques em NPC + respostas de dialogo (pass-through, so' observar)
		self.dialogAdvisor.AddClickListener(self._OnNpcClick)
		self.dialogAdvisor.AddAnswerListener(self._OnDialogAnswer)

	def _RestoreProgress(self):
		try:
			self._charNow = GuideLib.SafeCharName()
		except Exception:
			self._charNow = ''
		if self.progress.Load():
			for i, q in enumerate(self.quests):
				if q.name == self.progress.quest:
					self.questIdx = i
					break
		if self.questIdx < 0 and self.quests:
			self.questIdx = 0
			self.progress.Reset()
			self.progress.quest = self.quests[0].name
			self.progress.step = 0
		self._UpdateQuestText()
		self.RefreshSteps()

	# ================================================ ESTADO REAL DO JOGO ====
	def _SyncStart(self):
		# arranque: carrega o que o jogo ja' nos disse noutras sessoes,
		# junta ao registo local e SALTA para a missao que esta' a meio.
		sync = self.sync
		try:
			sys._mt2guide_activenotify = self._OnGameActiveQuest
			sys._mt2guide_donenotify = self._OnGameQuestDone
			sys._mt2guide_questsync = sync
		except:
			pass
		if sync is None or not sync.IsEnabled():
			self._SetStateText('JOGO: sem ligacao ao sistema de quests (usa .qdump para diagnostico)', GuideLib.COL_HINT)
			GuideLib.Log('[GuideUI] GuideQuestSync inativo (modulo de quests nao encontrado)')
			return
		sync.Load()
		self.doneLog.Merge(sync.CompletedNames())
		self._SetStateText('JOGO: ligado (%s) - feitas=%d ativas=%d' % (
			sync.modName, sync.CompletedCount(), sync.KnownCount()), GuideLib.COL_HINT)
		self.RefreshSteps()

	def QuestStateOf(self, q):
		# estado REAL da missao: 1) registo local (guia/jogo) 2) o log do
		# jogo (ativa/fecha) 3) progresso do guia (ultimo passo = feita)
		if q is None:
			return STATE_TODO
		if self.doneLog.IsDone(q.name, (getattr(q, 'name_pt', ''), getattr(q, 'subtitle', ''))):
			return STATE_DONE
		sync = self.sync
		if sync is not None and sync.IsEnabled():
			if sync.IsCompleted(q.name, getattr(q, 'name_pt', '')):
				return STATE_DONE
			if sync.IsActive(q.name, getattr(q, 'name_pt', '')):
				return STATE_ACTIVE
		try:
			if q is self.CurQuest() and q.steps and self.progress.step >= len(q.steps):
				return STATE_DONE
		except:
			pass
		return STATE_TODO

	def _SetStateText(self, text, color=None):
		self._lastStateText = text or ''
		try:
			self.dState.SetText(text or '')
			if color:
				self.dState.SetFontColor(color[0], color[1], color[2])
		except:
			pass

	def _RefreshGameStateLine(self):
		# linha "JOGO: ..." do detalhe do passo (estado + subtitulo real)
		q = self.CurQuest()
		if q is None:
			return
		sync = self.sync
		if sync is None or not sync.IsEnabled():
			return
		state = self.QuestStateOf(q)
		if state == STATE_DONE:
			self._SetStateText('JOGO: missao FEITA', GuideLib.COL_STEP_DONE)
			return
		m = sync.MatchQuest(q)
		if m is None:
			self._SetStateText('JOGO: %s (nao esta no log do jogo)' % (
				'a meio' if state == STATE_ACTIVE else 'por comecar'), GuideLib.COL_HINT)
			return
		name, title, score = m
		cnt = sync.CounterOf(name)
		if title:
			q.chapter = title           # subtitulo real (pesquisa/etiqueta)
		if cnt > 0:
			self._SetStateText('JOGO: a meio - contador real %d | %s' % (cnt, title), GuideLib.COL_HINT)
		else:
			self._SetStateText('JOGO: ativa | %s' % title, GuideLib.COL_HINT)

	# ------------------------------------------------- saltar p/ o jogo ----
	def _GameSig(self):
		# assinatura das quests ATIVAS no jogo (para so' ressincronizar
		# quando muda alguma coisa - nao pesa no cliente)
		sync = self.sync
		if sync is None:
			return ''
		try:
			names = sync.ActiveNames()
			if 0 < len(names) < 400:
				names.sort()
		except:
			names = []
		return '|'.join([str(n) for n in names])

	def OnFollowGame(self):
		if self.FollowGameQuest(force=True):
			self.info.SetText('segui a missao em curso no jogo')
		else:
			self.info.SetText('o jogo nao tem missao ativa (ou nao bate com a lista)')

	def FollowGameQuest(self, force=False):
		# salta para a missao que o JOGADOR tem a meio no jogo
		sync = self.sync
		if sync is None or not sync.IsEnabled():
			return False
		q = sync.ResolveActiveQuest(self.quests)
		if q is None:
			return False
		cur = self.CurQuest()
		if cur is not None and cur.name == q.name:
			return False
		if not force and not self.autoFollow:
			return False
		if not force and (GuideLib.Monotonic() - self._manualAt) < AUTO_FOLLOW_LOCK:
			return False      # o jogador escolheu a mao -> respeita
		# anti-loop: no maximo AUTO_JUMP_MAX saltos por minuto
		now = GuideLib.Monotonic()
		self._jumps = [t for t in self._jumps if now - t < 60.0]
		if not force and len(self._jumps) >= AUTO_JUMP_MAX:
			return False
		for i, qq in enumerate(self.quests):
			if qq.name != q.name:
				continue
			self._jumps.append(now)
			self._lastJump = now
			self.questIdx = i
			self.progress.Reset()
			self.progress.quest = q.name
			# acerta no PASSO pelo contador REAL do jogo
			guess = self._GuessStepFromGame(q)
			if guess is not None:
				self.progress.step, self.progress.killed = guess
			self._UpdateQuestText()
			self._ApplyStep()
			GuideLib.Log('[GuideUI] auto-follow: %s (passo %d, contador %d) [%s]' % (
				q.name, self.progress.step + 1, self.progress.killed,
				'jogo' if not force else 'manual'))
			self.info.SetText('missao em curso no jogo: %s' % (getattr(q, 'name_pt', '') or q.name))
			return True
		return False

	def _GuessStepFromGame(self, q):
		# usa o contador real do jogo para saber em que passo vamos
		sync = self.sync
		if sync is None:
			return None
		needs = []
		for i, st in enumerate(q.steps):
			need = self._StepCount(st, i) if st.IsCountStep() else 0
			needs.append(need or 0)
		try:
			return sync.GuessStep(q, needs)
		except Exception as e:
			GuideLib.Log('[GuideUI] GuessStep ERR: %r' % e)
			return None

	def _OnGameActiveQuest(self, name):
		# o cliente registou uma quest -> o jogador comecou/entrou nela
		GuideLib.Log('[GuideUI] jogo: quest ativa "%s"' % name)
		if not self.autoFollow:
			return
		self.FollowGameQuest()

	def _OnGameQuestDone(self, name):
		# o cliente diz que uma quest acabou -> fecha-a no guia
		self.doneLog.Mark(name)
		cur = self.CurQuest()
		if cur is not None and GuideLib.NormalizeText(name) in (
				GuideLib.NormalizeText(cur.name), GuideLib.NormalizeText(getattr(cur, 'name_pt', ''))):
			self.progress.step = len(cur.steps)
			self._ApplyStep()
			self.info.SetText('missao feita no jogo! (marcada como concluida)')
		self.RefreshSteps()
		try:
			self.picker.Refresh()
		except:
			pass

	def OnToggleAutoFollow(self):
		self.autoFollow = not self.autoFollow
		self.autoBtn.SetText('Segue:ON' if self.autoFollow else 'Segue:OFF')
		self.info.SetText('seguir a missao do jogo: %s' % ('ON' if self.autoFollow else 'OFF'))

	def OnMarkDone(self):
		q = self.CurQuest()
		if q is None:
			return
		self.doneLog.Mark(q.name)
		self.progress.step = len(q.steps)
		self._ApplyStep()
		self.info.SetText('"%s" marcada como FEITA' % (getattr(q, 'name_pt', '') or q.name))

	def OnDumpState(self):
		sync = self.sync
		if sync is None:
			return
		sync.DumpOnce()
		sync.DumpLive()
		q = self.CurQuest()
		self._RefreshGameStateLine()
		self.info.SetText('estado escrito: Data/quest_state.txt + syserr_guide.txt')
		GuideLib.Log('[GuideUI] estado do jogo: %s' % (self._lastStateText,))
		if q is not None:
			try:
				self.picker.Refresh()
			except:
				pass

	def ReloadDone(self):
		# reler o registo de missoes feitas (ex.: mudou de personagem)
		self.doneLog.Load()
		sync = self.sync
		if sync is not None and sync.IsEnabled():
			self.doneLog.Merge(sync.CompletedNames())
		try:
			self.picker.Refresh()
		except:
			pass

	def _SyncCounterFromGame(self, now):
		# o contador REAL do jogo (4/9 caes) atualiza o passo do guia
		sync = self.sync
		if sync is None or not sync.IsEnabled():
			return
		if now - self._lastCounterSync < 2.0:
			return
		self._lastCounterSync = now
		q = self.CurQuest()
		st = self.CurStep()
		if q is None or st is None:
			return
		if st.type not in ('kill', 'collect'):
			return
		guess = self._GuessStepFromGame(q)
		if guess is None:
			return
		idx, count = guess
		if idx > self.progress.step:
			# o jogo ja' vai mais a' frente -> acompanha
			self.progress.step = idx
			self.progress.killed = count
			self._ApplyStep()
			self.info.SetText('jogo: passo %d/%d (contador %d)' % (idx + 1, len(q.steps), count))
			GuideLib.Log('[GuideUI] contador do jogo -> passo %d, count %d [%s]' % (idx, count, q.name))
		elif idx == self.progress.step and count > self.progress.killed:
			self.progress.killed = count
			self._ApplyStep()

	def _UpdateQuestText(self):
		q = self.CurQuest()
		if q is None:
			self.qText.SetText('(nenhuma)')
			return
		label = _QuestLabel(q)
		if len(label) > 34:
			label = label[:33] + '...'
		self.qText.SetText(label)

	# ------------------------------------------------------- helpers -------
	def CurQuest(self):
		if 0 <= self.questIdx < len(self.quests):
			return self.quests[self.questIdx]
		return None

	def CurStep(self):
		q = self.CurQuest()
		if q is None:
			return None
		if 0 <= self.progress.step < len(q.steps):
			return q.steps[self.progress.step]
		return None

	def RefreshSteps(self):
		self.listBox.RemoveAllItems()
		q = self.CurQuest()
		if q is None:
			LIST_VER[0] += 1
			return
		for i, st in enumerate(q.steps):
			if i < self.progress.step:
				self.listBox.AppendItem(self.ListItemCls('[x] ' + st.text, GuideLib.COL_STEP_DONE))
			elif i == self.progress.step:
				tag = '[>] '
				need = self._StepCount(st, i)
				if st.IsCountStep() and need:
					tag = '[>] (%d/%d) ' % (self.progress.StepCount(self.progress.quest, i), need)
				self.listBox.AppendItem(self.ListItemCls(tag + st.text, GuideLib.COL_STEP_CUR))
			else:
				self.listBox.AppendItem(self.ListItemCls('[ ] ' + st.text, GuideLib.COL_STEP_TODO))
		LIST_VER[0] += 1

	def _ApplyStep(self, save=True):
		st = self.CurStep()
		q = self.CurQuest()
		if st is None or q is None:
			self.hud.SetStep('', None, '')
			self.dialogAdvisor.SetHint('')
			if q is None:
				self.info.SetText('sem missao ativa')
			else:
				self.info.SetText('missao concluida! (escolhe outra)')
				self.hud.SetStep('Missao concluida!', None, '')
			self.RefreshSteps()
			if save:
				self.progress.Save()
			return
		# passo novo -> cache dos mobs DESTE passo (mira + contagem auto)
		self._stepVnums = tuple(self._VnumList(st)) if st.IsCountStep() else ()
		self._autoChoiceTick = 0.0
		key = (self.progress.quest, self.progress.step)
		if key != self._killStepKey:
			self._killStepKey = key
			self._seenMobs = {}
			self._lastMarkVid = None   # passo novo -> trava o proximo mob
			self._ScanReset()
		lines = _Wrap2(st.text, 52)
		self.dText1.SetText(lines[0])
		self.dText2.SetText(lines[1] if len(lines) > 1 else '')
		# dica de dialogo + SUBTITULO/dica do passo (coluna 8: sub=...)
		hint = st.DialogHint()
		if getattr(st, 'sub', ''):
			hint = (hint + ' | ' + st.sub) if hint else st.sub
		# MISSAO DE CACA (1 de 2): diz O MOB DE CADA OPCAO e qual esta' a contar
		try:
			opts = st.HuntOptions()
			if len(opts) > 1:
				idx = self._CurOptIdx()
				if idx:
					o = st.OptionOf(idx)
					hunt = 'CACA: Op.%d = %s  (%d/%d)' % (
						idx, o.Label() if o is not None else '?',
						self.progress.killed, self._StepCount(st))
				else:
					hunt = 'CACA 1 de 2: carrega Op.1 ou Op.2 (mobs no texto do passo)'
				# (o mob e a quantidade de CADA opcao estao no texto do passo)
				hint = hunt
			elif len(st.HuntVnums()) > 1:
				ch = self.progress.ChoiceVnum(self.progress.quest, self.progress.step)
				hunt = 'CACA 1 de 2: %d/%d' % (self.progress.killed, self._StepCount(st))
				if ch:
					hunt += ' | a matar vnum %d' % ch
				else:
					hunt += ' | escolhe 1 (a mira segue-o)'
				hint = (hunt + ' | ' + hint) if hint else hunt
		except Exception:
			pass
		self.dHint.SetText(hint)
		self._RefreshOptButtons(st)
		self._RefreshGameStateLine()
		# alvo: prioridade 'a instancia viva
		tx, ty, label = self._ResolveTarget(st)
		self.hud.SetStep(st.text, (tx, ty) if tx is not None else None, label, st.type == 'kill')
		# dica de dialogo (aparece quando abrires o dialogo)
		if st.type in ('talk', 'turnin'):
			sub = 'Missao: %s' % q.name
		else:
			sub = q.name
		self.dialogAdvisor.SetHint(hint, sub if hint else '')
		# auto-avanco por chegada (so' passos de deslocamento)
		if st.type == 'goto' and tx is not None:
			self.hud.arriveCb = lambda: self._ArriveNext()
		else:
			self.hud.arriveCb = None
		if save:
			self.progress.Save()
		self.RefreshSteps()

	# ------------------------------------- missoes de caca "1 de 2" --------
	def _StepCount(self, st, stepIdx=None):
		# quantos mobs/items este passo pede. Nas MISSOES DE CACA o numero
		# depende da OPCAO que o jogador escolheu (ex: 10 ou 5).
		if st is None:
			return 0
		try:
			opts = st.HuntOptions()
		except Exception:
			opts = []
		if len(opts) > 1:
			si = self.progress.step if stepIdx is None else stepIdx
			idx = self.progress.ChoiceIndex(self.progress.quest, si)
			if idx:
				return st.OptionCount(idx)
			return opts[0].count or st.count
		return st.count

	def _CurOptIdx(self):
		return self.progress.ChoiceIndex(self.progress.quest, self.progress.step)

	def _StepOpts(self, st):
		try:
			return st.HuntOptions()
		except Exception:
			return []

	def _SetOptChoice(self, st, idx, why='', vnum=0, name=''):
		# fixa a opcao escolhida (gravada por personagem; sobrevive a sair)
		o = st.OptionOf(idx)
		if o is None:
			return False
		self.progress.SetChoice('op%d' % idx, self.progress.quest, self.progress.step)
		# se JA' sabemos o vnum deste mob por outro passo, aprende-o aqui
		if not o.vnum:
			v = GuideData.MobVnumByName(o.name)
			if v:
				o.vnum = v
		if vnum:
			self._LearnKillVnum(st, idx, vnum, name)
		msg = 'opcao %d escolhida: %s' % (idx, o.Label())
		if why:
			msg += ' (%s)' % why
		self.info.SetText(msg)
		GuideLib.Log('[caca] %s [%s passo %d]' % (msg, self.progress.quest, self.progress.step))
		self._ScanReset()
		return True

	def _AutoDetectOption(self, st, now):
		# Na missao de caca "1 de 2" ainda NAO sabemos qual o jogador
		# escolheu. O cliente diz quem ele tem TRAVADO (alvo) -> se o nome
		# desse mob bater com uma das opcoes, descobrimos tudo sozinhos.
		if now - self._autoChoiceTick < 1.0:
			return False
		self._autoChoiceTick = now
		try:
			vid, race, name = GuideLib.TargetInstance()
		except Exception:
			return False
		if not vid:
			return False
		idx = self._GuessOptByMob(st, name, race)
		if not idx:
			return False
		return self._SetOptChoice(st, idx, 'auto pelo alvo', race, name)

	def OnPickOpt1(self):
		self._PickOpt(1)

	def OnPickOpt2(self):
		self._PickOpt(2)

	def _PickOpt(self, idx):
		st = self.CurStep()
		if st is None:
			return
		if len(self._StepOpts(st)) < 2:
			self.info.SetText('este passo nao e uma missao de caca (1 de 2)')
			return
		# ajuda o guia: se o jogador tiver um mob travado, guarda tambem o
		# vnum desse mob para esta opcao (aprende e a mira passa a funcionar)
		vnum = 0
		name = ''
		try:
			_vid, vnum, name = GuideLib.TargetInstance()
		except Exception:
			vnum, name = 0, ''
		if self._SetOptChoice(st, idx, 'escolhi eu', vnum, name):
			self._ApplyStep()

	def _LearnKillVnum(self, st, idx, vnum, name):
		# APRENDE o vnum do mob (fica em Data/mobs_vnum.txt para sempre).
		# So' aprende quando o mob conhecido E' o mob da opcao: se o nome do
		# mob (o que o cliente diz) nao bater com o nome da opcao, o vnum
		# associado estaria errado e a mira apontava para o mob errado.
		if not vnum:
			return
		o = st.OptionOf(idx)
		if o is None:
			return
		on = GuideLib.NormalizeText(o.name or '')
		mn = GuideLib.NormalizeText(name or '')
		if mn and on and mn != on and mn not in on and on not in mn:
			return                  # outro mob -> nao aprende este vnum aqui
		if mn:
			GuideData.LearnMobVnum(name, vnum)
		elif on:
			GuideData.LearnMobVnum(o.name, vnum)
		if not o.vnum:
			o.vnum = int(vnum)
			GuideLib.Log('[caca] opcao %d agora tem vnum %d (%s)' % (idx, int(vnum), o.name))

	def _GuessOptByMob(self, st, name, race):
		# Descobre QUAL das 2 opcoes e' o mob que acabamos de matar/travar:
		#   1) pelo NOME que o cliente da' ao mob
		#   2) pelo VNUM que ja' conhecemos de outro passo
		# devolve o numero da opcao (0 = nao consigo saber)
		opts = self._StepOpts(st)
		if not opts:
			return 0
		n = GuideLib.NormalizeText(name or '')
		if len(n) >= 3:
			best = 0
			blen = 0
			for o in opts:
				on = GuideLib.NormalizeText(o.name or '')
				if not on or len(on) < 3:
					continue
				if on in n or n in on:
					if len(on) > blen:
						blen = len(on)
						best = o.idx
			if best:
				return best
		if race:
			for o in opts:
				if o.vnum and o.vnum == int(race):
					return o.idx
		return 0

	def _RefreshOptButtons(self, st):
		# Os botoes Op.1/Op.2 dizem o mob e o numero de cada opcao
		try:
			opts = self._StepOpts(st) if (st is not None and st.IsCountStep()) else []
			sig = tuple([(o.idx, o.count, o.name) for o in opts])
			if sig == self._optSig:
				return
			self._optSig = sig
			if len(opts) < 2:
				self.op1Btn.SetText('Op.1')
				self.op2Btn.SetText('Op.2')
				self.op1Btn.SetToolTipText('Só nas missoes de caca (escolhe 1 de 2)')
				self.op2Btn.SetToolTipText('Só nas missoes de caca (escolhe 1 de 2)')
				return
			self.op1Btn.SetText('Op.1 (%d)' % (opts[0].count or 0))
			self.op1Btn.SetToolTipText('ESCOLHI A OPCAO 1 -> %s' % opts[0].Label())
			self.op2Btn.SetText('Op.2 (%d)' % (opts[1].count or 0))
			self.op2Btn.SetToolTipText('ESCOLHI A OPCAO 2 -> %s' % opts[1].Label())
		except Exception as e:
			GuideLib.Log('[caca] botoes de opcao ERR: %r' % e)

	# ------------------------------------- varredura de instancias ---------
	def _ScanReset(self):
		# chamado 1x por tick: as posicoes dos mobs refrescam sempre, mas
		# dentro do MESMO tick so' se varre o cliente uma vez
		self._scanKey = None
		self._scanCache = {}
		self._nameCache = {}

	def _ScanNames(self, names):
		# {vid: (0, x, y, nome)} dos mobs cujo nome contem um dos `names`
		# (usado quando o vnum do mob ainda nao e' conhecido)
		key = tuple([str(n) for n in (names or []) if n])
		if not key:
			return {}
		if key not in self._nameCache:
			out = {}
			for nm in key:
				try:
					for (vid, x, y, name) in GuideLib.FindInstancesByName(nm):
						out[vid] = (0, x, y, name)
				except Exception:
					pass
			self._nameCache[key] = out
		return self._nameCache[key]

	def _ScanRaces(self, races):
		# {vid: (vnum, x, y, nome)} de todos os mobs aceites (varios vnums)
		key = tuple(sorted([int(r) for r in (races or []) if r]))
		if not key:
			self._scanKey = None
			self._scanCache = {}
			return {}
		if self._scanKey == key:
			return self._scanCache
		out = {}
		for r in key:
			try:
				for (vid, x, y, name) in GuideLib.FindInstancesByRace(r):
					out[vid] = (r, x, y, name)
			except Exception:
				pass
		self._scanKey = key
		self._scanCache = out
		return out

	def _VnumList(self, st):
		# todos os mobs (por VNUM) que CONTAM para este passo. Nas missoes de
		# caca com escolha ("1 de 2") o mob ja' escolhido passa a ser o unico.
		try:
			if st.IsCountStep():
				vnums = st.HuntVnums()
			else:
				vnums = [st.vnum] if st.vnum else []
		except Exception:
			vnums = [st.vnum] if st.vnum else []
		opts = self._StepOpts(st)
		if len(opts) > 1:
			idx = self._CurOptIdx()
			if idx:
				o = st.OptionOf(idx)
				# opcao escolhida: so' o mob dela conta (vazio = ainda sem vnum)
				return [o.vnum] if (o is not None and o.vnum) else []
			return [o.vnum for o in opts if o.vnum]
		if len(vnums) > 1:
			ch = self.progress.ChoiceVnum(self.progress.quest, self.progress.step)
			if ch and ch in vnums:
				return [ch]
		return list(vnums)

	def _NameList(self, st):
		# mobs deste passo cujo VNUM ainda nao sabemos: procuram-se pelo
		# NOME que o cliente da' a cada instancia. Sem opcao escolhida sao
		# os nomes das DUAS opcoes (a mira mostra os dois, cada um com o
		# numero do lado); depois da escolha so' fica o nome da escolhida.
		out = []
		try:
			if not st.IsCountStep():
				return out
			opts = self._StepOpts(st)
			idx = self._CurOptIdx()
			if len(opts) > 1:
				for o in opts:
					if idx and o.idx != idx:
						continue
					if o.vnum or not o.name:
						continue
					out.append((o.name, o.idx))
			elif not st.HuntVnums() and st.name:
				out.append((st.name, 0))
		except Exception:
			pass
		return out

	def _ResolveTarget(self, st):
		# devolve (x, y, etiqueta); instancia viva > pos da base de dados
		# (a pos escolhida e' a do REINO atual nas cidades 1/2)
		mx, my, mz = GuideLib.GetMyPosition()
		vnums = self._VnumList(st)
		if vnums:
			try:
				alive = self._ScanRaces(vnums)
				best = None
				bd = 1e18
				for vid, (r, x, y, name) in alive.items():
					dd = (x - mx) * (x - mx) + (y - my) * (y - my)
					if dd < bd:
						bd = dd
						best = (r, x, y, name)
				if best is not None:
					r, x, y, name = best
					return (x, y, self._StepLabel(st, name) + ' (a vista)')
			except Exception:
				pass
		# MISSOES DE CACA: sem vnum conhecido, procura pelo NOME que o
		# cliente da' a cada mob ("Cao Selvagem Feroz")
		for (nm, idx) in self._NameList(st):
			try:
				near = GuideLib.FindNearestByName(nm, mx, my)
			except Exception:
				near = None
			if near is None:
				continue
			return (near[1], near[2], self._StepLabel(st, near[3]) + ' (a vista)')
		pos = st.BestPoint(GuideLib.GetMyKingdom(), mx, my)
		if pos is not None:
			return (pos[0], pos[1], self._StepLabel(st, st.name))
		return (None, None, self._StepLabel(st, '') if st.IsCountStep() else '')

	def _StepLabel(self, st, name=None):
		# etiqueta do passo/mob: nome + contador REAL + "[1 de 2]"
		opts = self._StepOpts(st)
		idx = self._CurOptIdx()
		lbl = name or st.name or ''
		if len(opts) > 1 and idx:
			o = st.OptionOf(idx)
			if o is not None and o.name:
				lbl = o.name
		need = self._StepCount(st)
		if st.IsCountStep() and need:
			lbl = '%s %d/%d' % (lbl or '?', self.progress.killed, need)
		elif len(opts) > 1 and not idx:
			lbl = (lbl + ' [escolhe 1 de 2]').strip()
		return lbl

	def _ArriveNext(self):
		self._Advance()

	def _Advance(self):
		q = self.CurQuest()
		if q is None:
			return
		if self.progress.step + 1 < len(q.steps):
			self.progress.step += 1
			# NOTE: o contador e' POR PASSO (chave "missao|passo") -> ao mudar
			# de passo aparece o valor guardado desse passo; nunca se apaga
			# o que ja' foi feito (sobrevive a sair do jogo)
			self._ApplyStep()
			self.info.SetText('passo %d/%d' % (self.progress.step + 1, len(q.steps)))
		else:
			self.progress.step = len(q.steps)
			# FEITA: fica [x] na quest line e sai do filtro "A fazer"
			self.doneLog.Mark(q.name)
			self._ApplyStep()
			self.info.SetText('missao concluida! (marcada como feita)')
			try:
				self.picker.Refresh()
			except:
				pass
			self._PlayDone()

	def _PlayDone(self):
		try:
			for _mn, _mod in iter(sys.modules.items()):
				if buildin.hasattr(_mod, 'PlaySound'):
					try:
						_mod.PlaySound('sounds/effect/success.wav')
					except:
						pass
					return
		except:
			pass

	def _GoBack(self):
		if self.progress.step > 0:
			self.progress.step -= 1
			self._ApplyStep()

	# ------------------------------------------------------- callbacks -----
	def OnQuestChosen(self, q):
		# escolhida uma quest no seletor (tecla N / botao Missoes)
		for i, qq in enumerate(self.quests):
			if qq.name == q.name:
				self.questIdx = i
				self.progress.Reset()
				self.progress.quest = q.name
				self.progress.step = 0
				self._UpdateQuestText()
				self._ApplyStep()
				disp = getattr(q, 'name_pt', '') or q.name
				self.info.SetText('%s - %d passos, boa sorte!' % (disp, len(q.steps)))
				return

	def OnOpenQuestPicker(self):
		self.ReloadDone()          # estado real (feitas/ativas) sempre atual
		self.picker.SetQuests(self.quests)
		self.picker.Open()
		# abrir a quest line JA' ARMA a escrita -> escreve logo o nome
		try:
			arm_search()
		except Exception:
			pass

	def OnArmSearch(self, *a):
		# clique na linha "Pesquisar:" / botao Pesquisar -> modo escrita
		arm_search()

	def OnPrev(self):
		self._GoBack()

	def OnNext(self):
		self._Advance()

	def OnKillPlus(self):
		st = self.CurStep()
		if st is None:
			return
		if st.type in ('kill', 'collect'):
			self.progress.killed += 1
			need = self._StepCount(st)
			if need and self.progress.killed >= need:
				self.info.SetText('objectivo completo!')
				self._Advance()
				return
			self._ApplyStep()

	def OnPing(self):
		st = self.CurStep()
		tx, ty, label = self._ResolveTarget(st) if st is not None else (None, None, '')
		if tx is not None:
			mx, my, mz = GuideLib.GetMyPosition()
			try:
				eXLib.StoneDetect(mx, my, mz, tx, ty, GuideLib.DEFAULT_COMPASS, 0.0)
			except:
				pass
			self.info.SetText('ping para %s' % (label or '?'))
		else:
			self.info.SetText('este passo nao tem destino')

	def OnOpenQuestWindow(self):
		# N agora abre o SELETOR de quests do guia (a janela de missoes do
		# jogo e' suprimida: a tecla N nem lhe chega - ver init_guide.py)
		self.OnOpenQuestPicker()

	def OnToggleMarker(self):
		on = not self.hud.compassOn
		self.hud.SetCompass(on)
		self.markerBtn.SetText('Marc:ON' if on else 'Marc:OFF')

	def OnToggleTrail(self):
		on = not self.hud.trailOn
		self.hud.SetTrail(on)
		self.trailBtn.SetText('Rasto:ON' if on else 'Rasto:OFF')

	def OnToggleHud(self):
		on = not self.hud.enabled
		self.hud.SetEnabled(on)
		self.hudBtn.SetText('HUD:ON' if on else 'HUD:OFF')

	def OnToggleRecord(self):
		if self.recorder.active:
			self.recorder.Stop()
			self.recBtn.SetText('Gravar:OFF')
			self.info.SetText('gravacao parada (ver Data/quests_gravadas.txt)')
		else:
			if self.recorder.Start():
				self.recBtn.SetText('Gravar:ON')
				self.info.SetText('A GRAVAR: clica nos NPCs, responde dialogos')

	def OnReloadData(self):
		self.quests = GuideData.LoadAllQuests()
		self.questIdx = -1
		self._RestoreProgress()
		self.ReloadDone()
		try:
			self.picker.SetQuests(self.quests)
		except:
			pass
		tipos = GuideData.CountByType(self.quests)
		self.info.SetText('%d missoes (princ:%d secun:%d caca:%d)' % (
			len(self.quests), tipos.get(GuideData.TYPE_PRINCIPAL, 0),
			tipos.get(GuideData.TYPE_SECUNDARIA, 0), tipos.get(GuideData.TYPE_CACA, 0)))

	# ------------------------------------------------- observadores --------
	def _OnNpcClick(self, vid):
		# o utilizador clicou num NPC (pass-through; nos so' seguimos)
		st = self.CurStep()
		if st is None:
			return
		try:
			chr.SelectInstance(vid)
			race = chr.GetRace()
		except:
			race = 0
		self.recorder.OnNpcClick(vid)
		if st.type in ('talk', 'turnin'):
			# vnum certo OU passo sem vnum (professor/guardiao por reino)
			if (st.vnum and race == st.vnum) or not st.vnum:
				self._talkArmed = True
				self._waitingDialogForVnum = race

	def _OnDialogAnswer(self, answer_index):
		st = self.CurStep()
		if st is None:
			return
		self.recorder.OnDialogAnswer(answer_index, 0, self.dialogAdvisor.dialogCount)
		if st.type in ('talk', 'turnin') and self._talkArmed:
			self._talkArmed = False
			self._Advance()

	# ---------------------------------------------------------- update -----
	def OnUpdate(self):
		now = GuideLib.Monotonic()
		if now - self.lastTick < TICK:
			return
		self.lastTick = now
		# UMA varredura de instancias por tick: os mobs mexem-se e morrem,
		# por isso o retrato NAO pode ficar congelado entre passos (senao a
		# mira ficava parada e as mortes nunca eram contadas)
		self._ScanReset()
		# reinstala a ponte de teclas (INSERT/N) de 5 em 5s: o cliente pode
		# substituir player.OnKeyDown nos reloads do mundo
		try:
			if now - self._lastRearm > 5.0:
				self._lastRearm = now
				_rearm = getattr(sys, '_mt2guide_rearm', None)
				if _rearm is not None:
					_rearm()
		except:
			pass
		if not GuideLib.WorldSettled():
			return
		# mudou de PERSONAGEM? (login/logout dentro do mesmo cliente) ->
		# recarrega o progresso/mortes/missoes feitas DESSA char
		try:
			now_char = GuideLib.SafeCharName()
			if now_char and now_char != self._charNow:
				self._charNow = now_char
				self._ReloadForChar()
		except Exception:
			pass
		if not self._autoShown:
			# 1a vez no mundo: mostra o HUD e a janela (estilo RestedXP)
			self._autoShown = True
			try:
				self.hud.SetEnabled(True)
				self.Board.Show()
				k = GuideLib.GetMyKingdom()
				sync = 'jogo' if (self.sync is not None and self.sync.IsEnabled()) else 'sem jogo'
				self.info.SetText('INSERT = guia | N = quest line | %s | Reino: %s' % (
					sync, GuideLib.KINGDOM_NAMES.get(k, '?')))
				self._SyncStart()
				self.FollowGameQuest()
			except:
				pass
		# ---- ESTADO REAL DA CONTA/PERSONAGEM (sistema de quests do cliente)
		try:
			if self.sync is not None and self.sync.IsEnabled():
				self.sync.Poll(now)
				# missao em curso no jogo -> segue-a (sincroniza so' quando
				# o conjunto de missoes ativas muda)
				sig = self._GameSig()
				if sig != getattr(self, '_lastGameSig', ''):
					self._lastGameSig = sig
					self.FollowGameQuest()
				self._SyncCounterFromGame(now)
		except Exception as e:
			self._killLogTime = now
			GuideLib.Log('[GuideUI] sync ERR: %r' % e)
		# pesquisa: feita por teclado via hook (ver search_key); a linha
		# "Pesquisar:" da janela principal espelha o texto em tempo real
		st = self.CurStep()
		if st is None:
			return
		# refresca o alvo (NPCs vivos mexem-se / aparecem)
		tx, ty, label = self._ResolveTarget(st)
		if tx is not None:
			self.hud.SetStep(st.text, (tx, ty), label, st.type == 'kill')
		# MOBS DO PASSO: MIRA VERMELHA por cima + contagem automatica das
		# mortes ("matar/apanhar"), sempre gravada por personagem
		try:
			self._TrackMobs(st, now)
		except Exception as e:
			GuideLib.Log('[GuideUI] mobs ERR: %r' % e)
		# gravador: aprender kills de TODOS os mobs + dialogos
		try:
			self.recorder.PollKills()
		except:
			pass
		# armadilha de dialogo expira se nao houver dialogo em 10s
		if self._talkArmed:
			if self.dialogAdvisor.dialogCount > 0:
				self._talkTime = now
			elif now - getattr(self, '_talkTime', now) > 10.0:
				self._talkArmed = False

	# ----------------------------------------- mobs do passo (mira/kills) --
	def _MiraMobs(self, st, alive, mx, my, now):
		# MIRA VERMELHA: um alvo por cima de CADA mob que conta para o passo
		# (o mais proximo primeiro). Sem projecao no cliente nao desenha nada.
		marker = self.marker
		if marker is None:
			return
		if not marker.enabled or not alive:
			marker.Clear()
			return
		# com 2 opcoes ainda por escolher, cada mira diz a que opcao pertence
		opts = self._StepOpts(st)
		idx = self._CurOptIdx()
		multi = len(opts) > 1 and not idx
		items = []
		for vid, (r, x, y, name) in alive.items():
			d = GuideLib.dist(mx, my, x, y)
			if d > MIRA_RANGE:
				continue
			nm = name or st.name or '?'
			if multi:
				oi = self._GuessOptByMob(st, name, r)
				nm = '[%d] %s' % (oi, nm) if oi else nm
			items.append((d, vid, r, nm))
		if not items:
			marker.Clear()
			return
		items.sort()
		mobs = []
		for (d, vid, r, nm) in items[:MIRA_MAX]:
			mobs.append((vid, nm, True))
		# etiqueta so' no mais proximo: nome + contador REAL do passo
		near = items[0]
		lbl = self._StepLabel(st, near[3])
		mobs[0] = (near[1], lbl, True)
		marker.SetMobs(mobs)
		marker.Tick()
		# o jogo tambem trava o alvo no mob mais proximo (a seta vermelha
		# do cliente aparece-lhe em cima) - metodo comprovado do MT2Robs
		if now - self._lastTargetLock > 2.0:
			self._lastTargetLock = now
			best = near[1]
			if best != self._lastMarkVid:
				self._lastMarkVid = best
				try:
					eXLib.SetAttackTarget(best)
					GuideLib.Log('[marca] alvo travado vid=%s (%s)' % (best, st.name or '?'))
				except Exception:
					try:
						chr.SelectInstance(best)
					except Exception:
						pass
				try:
					tvx, tvy, tvz = eXLib.GetPixelPosition(best)
					GuideLib.MarkMob(tvx, tvy, tvz)
				except Exception:
					pass

	def _TrackMobs(self, st, now):
		# passo de matar/apanhar: conta as mortes REAIS e marca os mobs
		if not st.IsCountStep():
			self._stepVnums = ()
			if self.marker is not None:
				self.marker.Clear()
			return
		opts = self._StepOpts(st)
		isHunt = len(opts) > 1
		if isHunt and not self._CurOptIdx():
			# ainda nao sabemos qual das 2 opcoes o jogador tomou -> o ALVO
			# do cliente diz-nos isso (sem ele tocar em nada)
			if self._AutoDetectOption(st, now):
				self._ApplyStep()
		vnums = self._VnumList(st)
		names = self._NameList(st)
		if not vnums and not names:
			# passo sem vnum NEM nome de mob conhecido: diz UMA vez o que
			# fazer (o guia nunca conta mortes 'as cegas)
			if self._killStepKey != (self.progress.quest, self.progress.step, 'novnum'):
				self._killStepKey = (self.progress.quest, self.progress.step, 'novnum')
				GuideLib.Log('[GuideUI] passo %s SEM vnum (usa +1 manual/Escolher): %s [%s]' % (
					st.type, st.text, self.progress.quest))
				if isHunt and not self._CurOptIdx():
					self.info.SetText('missao de caca: carrega Op.1 ou Op.2')
				elif isHunt:
					self.info.SetText('trava um mob e carrega "Escolher" (aprender o vnum)')
			if self.marker is not None:
				self.marker.Clear()
			return
		mx, my, mz = GuideLib.GetMyPosition()
		alive = self._ScanRaces(vnums) if vnums else {}
		if names:
			# mobs que so' conhecemos pelo NOME ("Cao Selvagem Feroz")
			found = self._ScanNames([n for (n, i) in names])
			if found:
				alive = dict(alive)
				for vid in found:
					if vid not in alive:
						alive[vid] = found[vid]
		# ---- as miras (por cima dos mobs que contam) ----
		self._MiraMobs(st, alive, mx, my, now)
		# ---- mortes: um mob que estava vivo e desapareceu perto de nos ----
		kills = 0
		mudos = 0
		for vid in list(self._seenMobs.keys()):
			if vid in alive:
				continue
			old = self._seenMobs[vid]
			vnum = old[0]
			mname = old[3] if len(old) > 3 else ''
			d = GuideLib.dist(mx, my, old[1], old[2])
			if d >= KILL_RANGE:
				if now - self._killLogTime > 3.0:
					self._killLogTime = now
					GuideLib.Log('[kill] mob %s desapareceu longe (%.0fpx) -> ignora' % (vnum or mname or '?', d))
				continue
			if isHunt:
				idx = self._CurOptIdx()
				if not idx:
					# PRIMEIRA morte desta missao 1 de 2: e' ela que revela a
					# opcao escolhida (pelo nome do mob morto)
					idx = self._GuessOptByMob(st, mname, vnum)
					if idx:
						self._SetOptChoice(st, idx, 'auto pela morte', vnum, mname)
				if not idx:
					# nao sabemos qual dos dois mobs foi -> diz ao jogador o
					# que fazer (nao contamos nada errado)
					mudos += 1
					if now - self._killLogTime > 3.0:
						self._killLogTime = now
						self.info.SetText('mata e carrega Op.1 ou Op.2 (para eu saber qual e\')')
					continue
				# mortes do mob da OUTRA opcao nao contam para a missao
				other = self._GuessOptByMob(st, mname, vnum)
				if other and other != idx:
					mudos += 1
					continue
				o = st.OptionOf(idx)
				if o is not None and o.vnum and vnum and int(o.vnum) != int(vnum):
					mudos += 1
					continue
				# aprende o vnum deste mob para a opcao escolhida
				self._LearnKillVnum(st, idx, vnum, mname)
			kills += 1
			GuideLib.Log('[kill] mob (vnum %s%s) morto a %.0fpx -> CONTA' % (
				vnum, ', ' + mname if mname else '', d))
		# guarda o retrato deste instante (para a proxima comparacao)
		self._seenMobs = {}
		for vid, (r, x, y, nm) in alive.items():
			self._seenMobs[vid] = (r, x, y, nm)
		if mudos and now - self._killLogTime > 3.0:
			self._killLogTime = now
			GuideLib.Log('[kill] %d morte(s) nao contaram (opcao fixa/por decidir)' % mudos)
		if not kills:
			return
		need = self._StepCount(st)
		total = self.progress.AddStepCount(kills, self.progress.quest, self.progress.step)
		GuideLib.Log('[GuideUI] +%d mortes -> %d/%d (%s) [%s]' % (
			kills, total, need or 0, st.name or '?', self.progress.quest))
		if need and total >= need:
			self.info.SetText('objectivo completo! (auto)')
			self._Advance()
		else:
			self.info.SetText('%d/%d: %s (guardado)' % (
				total, need or 0, st.name or st.text))
			self._ApplyStep()

	def OnToggleMira(self):
		on = self.marker.Toggle() if self.marker is not None else False
		self._miraOn = on
		self.miraBtn.SetText('Mira:ON' if on else 'Mira:OFF')
		self.info.SetText('mira vermelha por cima dos mobs: %s' % ('ON' if on else 'OFF'))

	def OnChooseMob(self):
		# "Escolher": o mob que tenho TRAVADO (ou o mais perto) e' o mob
		# desta missao. Serve para (a) dizer qual a opcao escolhida e
		# (b) ENSINAR o vnum desse mob ao guia (fica guardado).
		st = self.CurStep()
		if st is None:
			return
		opts = self._StepOpts(st)
		isHunt = len(opts) > 1
		mx, my, mz = GuideLib.GetMyPosition()
		vid, race, name = (0, 0, '')
		try:
			vid, race, name = GuideLib.TargetInstance()
		except Exception:
			vid, race, name = (0, 0, '')
		if not vid:
			# sem alvo: usa o mob do passo mais perto de mim
			best = None
			bd = 1e18
			for v in st.HuntVnums():
				try:
					near = GuideLib.FindNearestByRace(v, mx, my)
				except Exception:
					near = None
				if near is None:
					continue
				d = GuideLib.dist(mx, my, near[1], near[2])
				if d < bd:
					bd = d
					best = (near[0], v, near[3], d)
			if best is None and isHunt:
				for (nm, oi) in self._NameList(st):
					try:
						near = GuideLib.FindNearestByName(nm, mx, my)
					except Exception:
						near = None
					if near is None:
						continue
					d = GuideLib.dist(mx, my, near[1], near[2])
					if d < bd:
						bd = d
						best = (0, 0, near[3], d)
			if best is None:
				self.info.SetText('nao vejo nenhum mob deste passo por aqui')
				return
			vid, race, name = best[0], best[1], best[2]
		if isHunt:
			idx = self._CurOptIdx()
			if not idx:
				idx = self._GuessOptByMob(st, name, race)
			if not idx:
				self.info.SetText('nao sei qual das 2 opcoes e\' (carrega Op.1 ou Op.2)')
				return
			if self._SetOptChoice(st, idx, 'escolhi eu', race, name):
				self._ApplyStep()
				return
		if not race and not name:
			self.info.SetText('nao consigo ver o mob que tens travado')
			return
		if len(st.HuntVnums()) > 1 and race:
			# passo antigo com 2 vnums (sem nomes): fixa este mob
			self.progress.SetChoice(race, self.progress.quest, self.progress.step)
		if name and race:
			GuideData.LearnMobVnum(name, race)
		GuideLib.Log('[mobs] mob fixado a mao: %s (vnum %s) [%s]' % (
			name or '?', race or '?', self.progress.quest))
		self.info.SetText('mob fixado: %s (vnum %s)' % (name or '?', race or '?'))
		self._ScanReset()
		self._ApplyStep()

	def OnDumpMobs(self):
		# diagnostico: que mobs vejo, quantos, a que distancia (+ opcoes)
		st = self.CurStep()
		if st is None:
			return
		opts = self._StepOpts(st)
		if len(opts) > 1:
			idx = self._CurOptIdx()
			GuideLib.Log('[mobs] MISSAO DE CACA (escolhe 1 de 2) [%s passo %d]:' % (
				self.progress.quest, self.progress.step))
			for o in opts:
				GuideLib.Log('[mobs]   op%d: mata %d x "%s"%s%s' % (
					o.idx, o.count or 0, o.name or '?',
					' vnum %d' % o.vnum if o.vnum else ' (vnum por descobrir)',
					'  <-- ESCOLHIDA' if o.idx == idx else ''))
			if not idx:
				GuideLib.Log('[mobs]   (Op.1/Op.2 decide qual conta; sem isso os dois ficam marcados)')
		vnums = self._VnumList(st) or st.HuntVnums()
		if not vnums and not self._NameList(st):
			self.info.SetText('este passo nao manda matar/apanhar mobs')
			return
		mx, my, mz = GuideLib.GetMyPosition()
		ch = self.progress.ChoiceVnum(self.progress.quest, self.progress.step)
		tot = 0
		for v in vnums:
			n = 0
			bestd = None
			try:
				for (vid, x, y, name) in GuideLib.FindInstancesByRace(v):
					n += 1
					d = GuideLib.dist(mx, my, x, y)
					if bestd is None or d < bestd:
						bestd = d
			except Exception:
				pass
			tot += n
			GuideLib.Log('[mobs] vnum %d: %d a vista%s%s | %s' % (
				v, n, ' (ESCOLHIDO)' if v == ch else '',
				' a %.0fm' % (bestd / 100.0) if bestd is not None else '',
				st.name or st.text))
		self.info.SetText('%d mobs a vista (%d vnums) - ver syserr_guide.txt' % (tot, len(vnums)))

	def _ReloadForChar(self):
		# mudou de PERSONAGEM: progresso, mortes guardadas, missoes feitas
		# e quests ativas do jogo sao TODOS deste char (nada de misturas)
		GuideLib.Log('[GuideUI] personagem agora: %s' % self._charNow)
		self.doneLog.Load()
		self.progress.Load()
		self._seenMobs = {}
		self._killStepKey = None
		self._ScanReset()
		try:
			if self.sync is not None and self.sync.IsEnabled():
				self.sync.Load()
				self.doneLog.Merge(self.sync.CompletedNames())
		except Exception:
			pass
		self._RestoreProgress()
		try:
			self.picker.Refresh()
		except Exception:
			pass
		self.info.SetText('progresso (mortes/missoes) carregado de %s' % self._charNow)

	def Close(self):
		# fechar o guia: desliga tambem o modo pesquisa e a quest line
		try:
			self.picker.Close()
		except:
			pass
		try:
			if self.marker is not None:
				self.marker.Clear()     # guia fechado -> sem miras no ecra
		except Exception:
			pass
		self.Board.Hide()


def _Wrap2(text, width):
	words = (text or '').split(' ')
	lines = []
	cur = ''
	for w in words:
		if len(cur) + len(w) + 1 > width and cur:
			lines.append(cur)
			cur = w
		else:
			cur = (cur + ' ' + w).strip()
	if cur:
		lines.append(cur)
	if not lines:
		lines = ['']
	return lines[:2]


class _MiniComp:
	# fabrica minimalista de widgets (nao depende do UIComponents do MT2Robs)
	def Text(self, parent, text, x, y, color):
		t = ui.TextLine()
		t.SetParent(parent)
		t.SetPosition(x, y)
		if color:
			t.SetFontColor(color[0], color[1], color[2])
		t.SetText(text)
		t.SetOutline()
		t.Show()
		return t

	def Button(self, parent, name, tooltip, x, y, func, Up, Over, Down):
		b = ui.Button()
		b.SetParent(parent)
		b.SetPosition(x, y)
		b.SetUpVisual(Up)
		b.SetOverVisual(Over)
		b.SetDownVisual(Down)
		b.SetText(name)
		b.SetToolTipText(tooltip)
		b.Show()
		b.SetEvent(func)
		return b

	def ComboBox(self, parent, text, x, y, width, func):
		c = ui.ComboBox()
		c.SetParent(parent)
		c.SetPosition(x, y)
		c.SetSize(width, 15)
		c.SetCurrentItem(text)
		c.SetEvent(func)
		c.Show()
		return c

	def ListBoxEx(self, parent, x, y, width, height):
		bar = ui.Bar()
		bar.SetParent(parent)
		bar.SetPosition(x, y)
		bar.SetSize(width + 20, height)
		bar.SetColor(1996488704)
		bar.Show()
		lb = ui.ListBoxEx()
		lb.SetParent(bar)
		lb.SetPosition(0, 0)
		lb.SetViewItemCount(11)
		lb.SetSize(width, height)
		lb.Show()
		sc = ui.ScrollBar()
		sc.SetParent(bar)
		sc.SetPosition(width + 5, 0)
		sc.SetScrollBarSize(height)
		sc.Show()
		lb.SetScrollBar(sc)
		return (bar, lb, sc)


try:
	instance
	instance.__class__ = QuestHelperWindow   # reload-safe
except NameError:
	instance = QuestHelperWindow()


_toggle_ts = {'g': 0.0, 'n': 0.0}


def _debounced(slot):
	# evita toggles duplos (as duas pontes de teclas podem disparar)
	try:
		t = GuideLib.Monotonic()
		if t - _toggle_ts[slot] < 0.35:
			return False
		_toggle_ts[slot] = t
	except:
		pass
	return True


def switch_state():
	if not _debounced('g'):
		return
	if instance.Board.IsShow():
		instance.Close()   # largar focos + fechar picker + esconder
	else:
		try:
			instance.Show()
		except:
			pass
		instance.Board.Show()


def toggle_picker():
	# tecla N: abre/fecha o seletor de quests (quest line)
	if not _debounced('n'):
		return
	try:
		instance.ReloadDone()   # estado real do personagem atualizado
		instance.picker.SetQuests(instance.quests)
		instance.picker.Toggle()
	except:
		pass


def _diag_game(L):
	# estado REAL da conta/personagem (o que o cliente sabe das quests)
	try:
		sync = getattr(instance, 'sync', None)
		if sync is None:
			L('[DIAG] sync: indisponivel')
			return
		L('[DIAG] sync: modulo=%s enabled=%s ready=%s ativas=%d feitas=%d' % (
			sync.modName, sync.IsEnabled(), sync.IsReady(),
			sync.KnownCount(), sync.CompletedCount()))
		L('[DIAG] tipos: %s' % (GuideData.CountByType(instance.quests),))
		L('[DIAG] feitas (guia)=%d | segue jogo=%s' % (
			instance.doneLog.Count(), instance.autoFollow))
		L('[DIAG] estado no jogo: %s' % (instance._lastStateText,))
		try:
			L('[DIAG] linhas do jogo: %s' % (instance.dState.GetText(),))
		except:
			pass
		q = instance.CurQuest()
		if q is not None:
			L('[DIAG] match da missao atual no jogo=%s' % (sync.MatchQuest(q),))
		sync.DumpLive()
	except Exception as e:
		L('[DIAG] _diag_game ERRO: %r' % e)


def dump_diag():
	# .qdiag -> diagnostico completo para o syserr_guide.txt
	try:
		L = GuideLib.Log
		L('[DIAG] mapa=%s reino=%s settled=%s' % (
			GuideLib.GetMapName(), GuideLib.GetMyKingdom(), GuideLib.WorldSettled()))
		L('[DIAG] pos jogador=%s' % (GuideLib.GetMyPosition(),))
		L('[DIAG] quests carregadas=%d' % len(instance.quests))
		_diag_game(L)     # estado real do jogo (mesmo sem passo ativo)
		q = instance.CurQuest()
		st = instance.CurStep()
		if q is None:
			L('[DIAG] sem quest ativa')
			return
		L('[DIAG] quest=%s passo=%d/%d killed=%d' % (
			q.name, instance.progress.step + 1, len(q.steps), instance.progress.killed))
		if st is None:
			L('[DIAG] passo atual: NENHEM (concluido?)')
			return
		L('[DIAG] passo tipo=%s vnum=%s count=%s' % (st.type, st.vnum, st.count))
		L('[DIAG] passo pos_geral=(%s, %s)' % (st.x, st.y))
		L('[DIAG] passo kpos reinos=%s' % sorted(st.kpos.keys()))
		L('[DIAG] PosForKingdom=%s' % (st.PosForKingdom(GuideLib.GetMyKingdom()),))
		try:
			tx, ty, label = instance._ResolveTarget(st)
			L('[DIAG] alvo resolvido=(%s, %s) label=%r' % (tx, ty, label))
		except Exception as e:
			L('[DIAG] _ResolveTarget ERRO: %r' % e)
		if st.vnum:
			try:
				near = GuideLib.FindNearestByRace(st.vnum, *GuideLib.GetMyPosition()[:2])
				L('[DIAG] instancia viva=%s' % (near,))
			except Exception as e:
				L('[DIAG] FindNearest ERRO: %r' % e)
		L('[DIAG] hud enabled=%s trail=%s area=%s target=%s' % (
			instance.hud.enabled, instance.hud.trailOn, instance.hud.areaMode, instance.hud.target))
	except Exception as e:
		try:
			GuideLib.Log('[DIAG] ERRO: %r' % e)
		except:
			pass
