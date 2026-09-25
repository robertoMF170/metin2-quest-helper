# -*- coding: utf-8 -*-
# MT2Guide - GuideMark.py
# MIRA VERMELHA por cima dos mobs que a missao atual manda matar.
#
# Como funciona:
#   - a janela principal diz QUAIS mobs contam (vid do mob + nome)
#   - a posicao no ecra vem do proprio cliente
#     (chr.GetProjectPosition -> GuideLib.ProjectToScreen)
#   - por cada mob aparece uma mira (anel vermelho + cruz) e, no mais
#     proximo, o nome com o contador REAL do passo (ex: "Raposa 3/10")
#
# Todas as chamadas ao cliente estao protegidas: se o cliente nao souber
# projetar (ou nao aceitar a flag 'not_pick', que impede a camada de tapar
# os cliques no mundo), o guia continua a funcionar sem miras.
import GuideLib

chr = GuideLib.chr
app = GuideLib.app
ui = GuideLib.ui

POOL_MAX = 16       # maximo de miras desenhadas ao mesmo tempo
MIRA_DX = -32       # centrado: imagem 64x64 -> -32 para centrar horizontal
MIRA_DY = -64       # pixeis ACIMA do mob (por cima da cabeca) - era -104 (flutuava)
MIRA_W = 64         # tamanho da imagem da mira (para centrar)
MIRA_H = 64
LAYER_W = 2048      # tamanho da camada transparente (cobre qualquer resolucao)
LAYER_H = 1536


class MobMarker(object):

	def __init__(self):
		self.enabled = True        # botao "Mira:ON/OFF"
		self.Board = None          # camada transparente (topo do ecra)
		self._items = []           # pool de (imagebox, textline)
		self._mobs = []            # [(vid, label, chosen)]
		self._ready = False
		self._failed = False
		self._warned = False
		self._imgPath = None

	# -------------------------------------------------------- camada -------
	def _Ensure(self):
		if self._ready:
			return True
		if self._failed:
			return False
		try:
			try:
				self.Board = ui.Window()
			except Exception:
				self.Board = None
			if self.Board is None:
				self._Failed('ui.Window indisponivel')
				return False
			try:
				self.Board.SetSize(LAYER_W, LAYER_H)
				self.Board.SetPosition(0, 0)
			except Exception:
				pass
			try:
				self.Board.AddFlag('not_pick')   # NAO apanha cliques do jogo
			except Exception as e:
				# sem 'not_pick' esta camada tapava o mundo -> nao a usamos
				self._Failed('cliente sem flag not_pick (%r)' % e)
				return False
			try:
				self.Board.AddFlag('float')
			except Exception:
				pass
			try:
				self.Board.Show()
			except Exception:
				pass
			self._ready = True
			return True
		except Exception as e:
			self._Failed('erro a criar a camada: %r' % e)
			return False

	def _Failed(self, why):
		self._failed = True
		self._ready = False
		try:
			if self.Board is not None:
				self.Board.Hide()
		except Exception:
			pass
		GuideLib.Log('[GuideMark] miras desligadas: %s' % why)

	def _Warn(self):
		if self._warned:
			return
		self._warned = True
		GuideLib.Log('[GuideMark] sem posicao no ecra para os mobs (miras nao aparecem)')

	def _ImgPath(self):
		if self._imgPath is None:
			self._imgPath = GuideLib.MiraImagePath()
		return self._imgPath

	def _Item(self, i):
		# cria (se preciso) a mira numero i
		while len(self._items) <= i:
			try:
				img = ui.ExpandedImageBox()
			except Exception:
				img = ui.ImageBox()
			img.SetParent(self.Board)
			try:
				img.LoadImage(self._ImgPath())
			except Exception as e:
				self._Failed('imagem da mira nao carregou (%r)' % e)
				return None
			img.Hide()
			txt = ui.TextLine()
			txt.SetParent(self.Board)
			try:
				txt.SetFontColor(*GuideLib.COL_MIRA_TEXT)
				txt.SetOutline()
			except Exception:
				pass
			txt.Hide()
			self._items.append((img, txt))
		return self._items[i]

	# ------------------------------------------------------ interface ------
	def SetEnabled(self, on):
		self.enabled = bool(on)
		if not self.enabled:
			self.HideAll()

	def Toggle(self):
		self.SetEnabled(not self.enabled)
		return self.enabled

	def SetMobs(self, mobs):
		# mobs: [(vid, etiqueta, escolhido)] - o mais proximo primeiro
		self._mobs = list(mobs or [])

	def Clear(self):
		self._mobs = []

	def HideAll(self):
		self._mobs = []
		for (img, txt) in self._items:
			try:
				img.Hide()
			except Exception:
				pass
			try:
				txt.Hide()
			except Exception:
				pass

	# ---------------------------------------------------------- update -----
	def Tick(self):
		# chamado a CADA FRAME (a posicao do mob muda com camara/movimento)
		# -> tem de ser rapido e acompanhar o mob como a cena das missoes dos NPCs.
		# Antes so corria a cada 0.25s e fazia break no 1o mob fora do ecra
		# -> lag + miras estaticas + falhava quando rodavas a camara.
		if not self.enabled or not self._mobs:
			self.HideAll()
			return
		if not self._Ensure():
			return
		shown = 0
		hasOffscreen = False
		for mob in self._mobs[:POOL_MAX]:
			vid = mob[0]
			label = mob[1] if len(mob) > 1 else ''
			p = GuideLib.ProjectToScreen(vid)
			if p is None:
				hasOffscreen = True
				continue  # mob fora do ecra / atras da camara -> salta, mostra o proximo
			# filtra posicoes absurdamente fora do ecra (evita mira no infinito)
			px, py = p[0], p[1]
			if px < -200 or py < -200 or px > 4000 or py > 3000:
				hasOffscreen = True
				continue
			it = self._Item(shown)
			if it is None:
				break
			img, txt = it
			x = int(px) + MIRA_DX
			y = int(py) + MIRA_DY
			try:
				img.SetPosition(x, y)
				img.Show()
			except Exception:
				continue
			if shown == 0 and label:
				# etiqueta so' na mira do mob mais proximo no ecra
				try:
					txt.SetPosition(x + 18, y - 14)
					txt.SetText(label)
					txt.Show()
				except Exception:
					try:
						txt.Hide()
					except Exception:
						pass
			else:
				try:
					txt.Hide()
				except Exception:
					pass
			shown += 1
			if shown >= POOL_MAX:
				break
		if shown == 0 and hasOffscreen:
			# nenhum no ecra mas ha mobs vivos fora de vista -> avisa 1x
			self._Warn()
		for i in range(shown, len(self._items)):
			img, txt = self._items[i]
			try:
				img.Hide()
			except Exception:
				pass
			try:
				txt.Hide()
			except Exception:
				pass


try:
	marker
	marker.__class__ = MobMarker        # reload-safe
except NameError:
	marker = MobMarker()
