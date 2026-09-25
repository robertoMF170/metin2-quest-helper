# -*- coding: utf-8 -*-
# MT2Guide - GuideNav.py
# HUD de navegacao estilo RestedXP:
#  - seta no ecra (roda consoante a direccao do objetivo) + distancia
#  - apontador 3D na cena (efeito compasso do cliente, eXLib.StoneDetect)
#  - segue a POSICAO VIVA do NPC/mob quando esta a vista (senao usa as
#    coordenadas gravadas na base de dados)
import sys

try:
	import __builtin__ as buildin
except ImportError:
	import builtins as buildin

import GuideLib
import eXLib

player = GuideLib.player
chr = GuideLib.chr
app = GuideLib.app
ui = GuideLib.ui

POLL = 0.15          # seg entre actualizacoes do HUD
COMPASS_EVERY = 3.0  # seg entre apontadores 3D
ARRIVE_DIST = 300.0  # px -> considerado "chegou" (para passos goto/talk)
MARKER_BY_NAME = True  # procurar alvo por nome quando nao ha vnum
TRAIL_EVERY = 4.0    # seg entre redesenhos da linha no chao
TRAIL_STEP = 500.0   # px entre pontos da linha
TRAIL_MAX = 10       # maximo de pontos da linha
AREA_RADIUS = 1800.0  # px -> raio da area de spawn (passos kill)
AREA_DOTS = 12       # pontos do anel de area


class GuideHUD(ui.ScriptWindow):

	def __init__(self):
		ui.ScriptWindow.__init__(self)
		self.lastPoll = 0.0
		self.lastCompass = 0.0
		self.lastTrail = 0.0
		self.enabled = True          # HUD visivel
		self.compassOn = True        # apontador 3D
		self.trailOn = False         # linha no chao (OFF por defeito: e'
		                              # experimental - ligar so' com o botao)
		self.areaMode = False        # desenhar anel de area (passos kill)
		self.stepText = ''
		self.target = None           # (x, y) em coords de pixel
		self.targetLabel = ''
		self.arriveCb = None         # chamado quando chega ao destino
		self._cameraFn = None
		self._probeCamera()

		self.Board = ui.ThinBoard(layer='TOP_MOST')
		self.Board.SetSize(300, 64)
		self.Board.SetPosition(20, 20)
		self.Board.AddFlag('float')
		self.Board.AddFlag('movable')
		self.Board.Hide()

		self.Arrow = ui.ExpandedImageBox()
		self.Arrow.SetParent(self.Board)
		self.Arrow.SetPosition(10, 12)
		self.Arrow.LoadImage(GuideLib.ArrowImagePath())
		self.Arrow.Show()

		self.Step1 = ui.TextLine()
		self.Step1.SetParent(self.Board)
		self.Step1.SetPosition(62, 10)
		self.Step1.SetFontColor(*GuideLib.COL_STEP_CUR)
		self.Step1.SetOutline()
		self.Step1.SetText('')
		self.Step1.Show()

		self.Step2 = ui.TextLine()
		self.Step2.SetParent(self.Board)
		self.Step2.SetPosition(62, 26)
		self.Step2.SetFontColor(*GuideLib.COL_INFO)
		self.Step2.SetOutline()
		self.Step2.SetText('')
		self.Step2.Show()

		self.Dist = ui.TextLine()
		self.Dist.SetParent(self.Board)
		self.Dist.SetPosition(62, 42)
		self.Dist.SetFontColor(*GuideLib.COL_DIST)
		self.Dist.SetOutline()
		self.Dist.SetText('')
		self.Dist.Show()

		self.Show()

	def _probeCamera(self):
		# alguns clientes expoe a rotacao da camera; se existir, a seta do
		# ecra fica sempre certa mesmo com a camera rodada.
		for mod, names in ((app, ('GetCameraRotation', 'GetRotatingAngle', 'GetCameraAngle')),
		                   (GuideLib, ('grp',))):
			for n in names:
				try:
					fn = getattr(mod, n, None)
					if buildin.callable(fn):
						self._cameraFn = fn
						return
				except:
					pass
		# grp.GetCameraRotation? (probe tardio, grp pode carregar depois)
		try:
			import grp as _grp
			for n in ('GetCameraRotation', 'GetRotatingAngle', 'GetCameraAngle'):
				fn = getattr(_grp, n, None)
				if buildin.callable(fn):
					self._cameraFn = fn
					return
		except:
			pass

	# ---------------------------------------------------------- interface --
	def SetStep(self, text, target_xy, label='', area=False):
		self.stepText = text or ''
		self.target = target_xy
		self.targetLabel = label or ''
		if area != self.areaMode:
			self.areaMode = bool(area)
			self.lastTrail = 0.0   # muda de modo -> redesenha ja' o anel
		lines = _Wrap(self.stepText, 40)
		self.Step1.SetText(lines[0])
		self.Step2.SetText(lines[1] if len(lines) > 1 else '')

	def SetEnabled(self, on):
		self.enabled = bool(on)
		if self.enabled:
			self.Board.Show()
		else:
			self.Board.Hide()

	def SetCompass(self, on):
		self.compassOn = bool(on)

	def SetTrail(self, on):
		self.trailOn = bool(on)

	def Ping(self):
		# dispara UM apontador 3D ja' (botao "ping" na janela principal)
		self.lastCompass = 0.0

	# ----------------------------------------------------------- update ----
	def _CameraAngle(self):
		if self._cameraFn is None:
			return 0.0
		try:
			v = self._cameraFn()
			try:
				return float(v)
			except:
				return 0.0
		except:
			return 0.0

	def OnUpdate(self):
		self.Tick()

	def Tick(self):
		# corpo do update: chamado pelo proprio OnUpdate E pela janela
		# principal (GuideUI.OnUpdate corre SEMPRE; nem todos os clientes
		# chamam OnUpdate de windows sem pai -> assim o HUD nunca congela)
		if not self.enabled or not GuideLib.WorldSettled():
			return
		now = GuideLib.Monotonic()
		if now - self.lastPoll < POLL:
			return
		self.lastPoll = now

		tx, ty = self._LiveTarget()
		if tx is None:
			if self.targetLabel:
				# sem posicao na BD / mob nao visivel: mostra a etiqueta
				# (nome + contagem) em vez de "sem destino"
				self.Dist.SetText('%s  a procurar mob...' % self.targetLabel)
			else:
				self.Dist.SetText('sem destino' if self.stepText else '')
			return

		mx, my, mz = GuideLib.GetMyPosition()
		d = GuideLib.dist(mx, my, tx, ty)

		# chegada?
		if d <= ARRIVE_DIST and self.arriveCb is not None:
			try:
				cb = self.arriveCb
				self.arriveCb = None
				cb()
			except:
				pass
			return

		self.Dist.SetText('%s  %dm' % (self.targetLabel, int(d / 100)))

		# seta do ecra: angulo a partir do norte (y- = norte no atlas),
		# rodando no sentido dos ponteiros; compensa a camera se der para.
		_m = GuideLib.math
		dx = tx - mx
		dy = ty - my
		ang = _m.atan2(dx, -dy) * 180.0 / _m.pi
		ang = (ang - self._CameraAngle()) % 360.0
		try:
			self.Arrow.SetRotation(ang)
		except:
			pass

		# apontador 3D na cena (o mesmo efeito do compasso de metins)
		if self.compassOn and now - self.lastCompass >= COMPASS_EVERY:
			self.lastCompass = now
			try:
				eXLib.StoneDetect(mx, my, mz, tx, ty, GuideLib.DEFAULT_COMPASS, 0.0)
			except:
				pass

		# LINHA no chao (pontos que assentam no terreno, sobem montanhas)
		# + ANEL de area de spawn nos passos de kill
		if self.trailOn and now - self.lastTrail >= TRAIL_EVERY:
			self.lastTrail = now
			self._DrawTrail(mx, my, mz, tx, ty)

	def _DrawTrail(self, mx, my, mz, tx, ty):
		# pontos com o efeito do compasso (o MESMO ja' usado pelo Marc,
		# comprovado): cada um fica NO CHAO na sua posicao (o terreno
		# decide a altura -> considera montanhas)
		try:
			eff = GuideLib.DEFAULT_COMPASS
			d = GuideLib.dist(mx, my, tx, ty)
			if d > 700.0:
				n = int(d / TRAIL_STEP)
				if n > TRAIL_MAX:
					n = TRAIL_MAX
				for i in range(1, n + 1):
					t = float(i) / float(n + 1)
					px = mx + (tx - mx) * t
					py = my + (ty - my) * t
					try:
						eXLib.StoneDetect(mx, my, mz, px, py, eff, 0.0)
					except:
						return
			if self.areaMode:
				_m = GuideLib.math
				for k in range(AREA_DOTS):
					a = 2.0 * _m.pi * k / AREA_DOTS
					ax = tx + AREA_RADIUS * _m.cos(a)
					ay = ty + AREA_RADIUS * _m.sin(a)
					try:
						eXLib.StoneDetect(mx, my, mz, ax, ay, eff, 0.0)
					except:
						return
		except:
			pass

	def _LiveTarget(self):
		# o alvo pode ser (x,y) fixo da base de dados; devolve sempre esse
		# (a metadata de vivo/por-nome e' resolvida pela janela principal
		# antes de chamar SetStep).
		return self.target


def _Wrap(text, width):
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


try:
	hud
	hud.__class__ = GuideHUD   # reload-safe
except NameError:
	hud = GuideHUD()
