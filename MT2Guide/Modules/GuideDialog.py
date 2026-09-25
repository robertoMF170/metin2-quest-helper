# -*- coding: utf-8 -*-
# MT2Guide - GuideDialog.py
# Advisor de dialogos: diz QUEADRADO escolher quando falas com um NPC.
# - Faz hook PASS-THROUGH de event.SelectAnswer (o utilizador clica, nos
#   so' observamos para acompanhar o progresso) e de net.SendOnClickPacket
#   (cliques em NPCs).
# - Painel flutuante: enquanto um dialogo estiver aberto mostra a dica
#   "DIALOGO: escolhe o quadrado [2] Kabul Et".
# Nao responde NADA automaticamente -> guia puro.
import sys

try:
	import __builtin__ as buildin
except ImportError:
	import builtins as buildin

import GuideLib
import eXLib

player = GuideLib.player
chr = GuideLib.chr
net = GuideLib.net
app = GuideLib.app
ui = GuideLib.ui
event = GuideLib.event

POLL = 0.2   # seg entre verificações do estado do dialogo


class DialogAdvisor(ui.ScriptWindow):

	def __init__(self):
		ui.ScriptWindow.__init__(self)
		self.lastPoll = 0.0
		self.dialogCount = 0
		self.hint = ''
		self.clickListeners = []     # f(vid)
		self.answerListeners = []    # f(answer_index)
		self._installed = False
		self._visibleSince = 0.0

		# ---- painel de dica (fundo + texto) ----
		self.Board = ui.ThinBoard(layer='TOP_MOST')
		self.Board.SetSize(340, 40)
		self.Board.AddFlag('float')
		self.Board.SetPosition(0, 200)
		self.Board.Hide()

		self.Text = ui.TextLine()
		self.Text.SetParent(self.Board)
		self.Text.SetPosition(10, 7)
		self.Text.SetFontColor(*GuideLib.COL_HINT)
		self.Text.SetOutline()
		self.Text.SetText('')
		self.Text.Show()

		self.Text2 = ui.TextLine()
		self.Text2.SetParent(self.Board)
		self.Text2.SetPosition(10, 22)
		self.Text2.SetFontColor(*GuideLib.COL_INFO)
		self.Text2.SetOutline()
		self.Text2.SetText('')
		self.Text2.Show()

		self.InstallHooks()
		self.Show()   # ScriptWindow visivel -> OnUpdate corre

	# ------------------------------------------------------------ hooks --
	def InstallHooks(self):
		if self._installed:
			return
		self._installed = True
		# event.SelectAnswer(index, answer) -> pass-through + notificar
		try:
			self._origSelect = event.SelectAnswer
			def _wrapSelect(*args, **kw):
				try:
					idx = args[1] if len(args) > 1 else 0
					for fn in self.answerListeners:
						try:
							fn(idx)
						except:
							pass
				except:
					pass
				return self._origSelect(*args, **kw)
			event.SelectAnswer = _wrapSelect
		except Exception as e:
			GuideLib.Log('[Dialog] hook SelectAnswer ERR: %r' % e)
		# net.SendOnClickPacket(vid) -> pass-through + notificar
		try:
			self._origClick = net.SendOnClickPacket
			def _wrapClick(*args, **kw):
				try:
					if args:
						for fn in self.clickListeners:
							try:
								fn(args[0])
							except:
								pass
				except:
					pass
				return self._origClick(*args, **kw)
			net.SendOnClickPacket = _wrapClick
		except Exception as e:
			GuideLib.Log('[Dialog] hook OnClick ERR: %r' % e)

	def AddClickListener(self, fn):
		if fn not in self.clickListeners:
			self.clickListeners.append(fn)

	def AddAnswerListener(self, fn):
		if fn not in self.answerListeners:
			self.answerListeners.append(fn)

	# ------------------------------------------------------------- dica --
	def SetHint(self, hint, sub=''):
		self.hint = hint
		self._sub = sub

	_sub = ''

	def _Layout(self):
		# centro-horizontal, acima do chat
		try:
			w, h = app.GetResolution()
			l = (w - self.Board.GetWidth()) / 2
			self.Board.SetPosition(l, h - 220)
		except:
			pass

	# ---------------------------------------------------------- update ----
	def OnUpdate(self):
		now = GuideLib.Monotonic()
		if now - self.lastPoll < POLL:
			return
		self.lastPoll = now

		cnt = 0
		try:
			c = eXLib.GetDialogAnswerCount()
			if buildin.isinstance(c, int) and c > 0:
				cnt = c
		except:
			cnt = 0

		if cnt != self.dialogCount:
			if cnt > 0 and self.dialogCount == 0:
				self._visibleSince = now
			self.dialogCount = cnt

		if cnt > 0 and self.hint:
			if not self.Board.IsShow():
				self._Layout()
				self.Board.Show()
			self.Text.SetText(self.hint)
			self.Text2.SetText(self._sub or ('(%d opcoes visiveis)' % cnt))
		else:
			if self.Board.IsShow():
				self.Board.Hide()

	def Close(self):
		self.Board.Hide()


try:
	advisor
	advisor.__class__ = DialogAdvisor   # reload-safe: reutiliza a janela viva
except NameError:
	advisor = DialogAdvisor()


def switch_state():
	if advisor.Board.IsShow():
		advisor.Board.Hide()
	else:
		advisor.Show()
