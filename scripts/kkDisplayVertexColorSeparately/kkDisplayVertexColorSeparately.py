# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals

import os, sys, traceback
from functools import wraps

import maya.cmds as mc
import maya.mel as mel
import maya.api.OpenMaya as om2
import maya.OpenMayaUI as omUI

from maya.app.general.mayaMixin import MayaQWidgetBaseMixin

try:
	from PySide2.QtWidgets import QMainWindow, QApplication
	from PySide2.QtGui import QPainterPath, QRegion, QIcon
	from PySide2.QtUiTools import QUiLoader
	from PySide2.QtCore import Qt, QPoint, QRect
	from shiboken2 import wrapInstance
except ImportError:
	from PySide.QtGui import QMainWindow, QApplication, QPainterPath, QRegion, QIcon
	from PySide.QtUiTools import QUiLoader
	from PySide.QtCore import Qt, QPoint, QRect
	from shiboken import wrapInstance


#----------------------------------------------------------------------------------------------------------------------
# 関数の前後にundoInfoのopenChunkとcloseChunkを実行するデコレーター
def openCloseChunk(func):
	@wraps(func)
	def wrapper(*args, **kargs):
		action = None
		try:
			mc.undoInfo(openChunk=True)
			action = func(*args, **kargs)
		except:
			print(traceback.format_exc())
			pass
		finally:
			mc.undoInfo(closeChunk=True)
			return action

	return wrapper


#----------------------------------------------------------------------------------------------------------------------


class kkDisplayVertexColorSeparatelyWindow(MayaQWidgetBaseMixin, QMainWindow):
	targetObj           = None
	targetObjMesh       = None
	targetObjVtxCount   = None
	targetObjVtxIdxList = None

	jobNum_attributeChange_R = 0
	jobNum_attributeChange_G = 0
	jobNum_attributeChange_B = 0
	jobNum_attributeChange_A = 0
	jobNum_attributeChange_Base = 0

	jobNum_nodeDeleted_R = 0
	jobNum_nodeDeleted_G = 0
	jobNum_nodeDeleted_B = 0
	jobNum_nodeDeleted_A = 0

	jobNum_otherSceneOpened = 0

	callbackID_nameChanged = None

	baseColorSet        = ""
	baseColorSerRep     = "RGBA"
	baseColorBeforeEdit = None

	attrDispColor  = 0
	pOption_matChl = ""
	pOption_matBld = ""

	isHistoryDeleted = True

	# 中間オブジェクトを持っているか
	hasIntermediateObject = False

	mouseCursorPos = QPoint(0, 0)
	isDragging = False

	# 各ボタンのOnOff時のサイズを定義しておく
	btn_R_checkOnRect  = QRect(18, 72, 164, 36)
	btn_R_checkOffRect = QRect(10, 70, 180, 40)

	btn_G_checkOnRect  = QRect(18, 117, 164, 36)
	btn_G_checkOffRect = QRect(10, 115, 180, 40)

	btn_B_checkOnRect  = QRect(18, 162, 164, 36)
	btn_B_checkOffRect = QRect(10, 160, 180, 40)

	btn_A_checkOnRect  = QRect(18, 207, 164, 36)
	btn_A_checkOffRect = QRect(10, 205, 180, 40)

	uiFIle = None

	def __init__(self, parent=None):
		# すでにウィンドウ開いていた場合閉じておく
		self.deleteInstances()

		selList = om2.MGlobal.getActiveSelectionList()

		mDagPath, _ = selList.getComponent(0)

		self.targetObj     = om2.MFnTransform(mDagPath)
		self.targetObjMesh = om2.MFnMesh(mDagPath)

		self.targetObjVtxCount   = self.targetObjMesh.numVertices
		self.targetObjVtxIdxList = xrange(self.targetObjVtxCount)

		mObj = mDagPath.node()

		# ターゲットのオブジェクト名が変更されたcallbackを受けて実行する関数を登録
		self.callbackID_nameChanged = om2.MNodeMessage.addNameChangedCallback(mObj, self.targetObjNameChangedCallback)


		super(kkDisplayVertexColorSeparatelyWindow, self).__init__(parent)
		self.setupUI()


		# displayColorsを取得して残しておきつつ、確認できるようにカラー表示をONにしておく
		self.attrDispColor = mc.getAttr("%s.displayColors"%self.targetObjMesh.fullPathName())
		mc.setAttr("%s.displayColors"%self.targetObjMesh.fullPathName(), 1)


		# colorMaterialChannelとmaterialBlendを取得して残しておきつつ変更する
		self.pOption_matChl = mc.polyOptions(q=True, colorMaterialChannel=True, gl=False)[0]
		self.pOption_matBld = mc.polyOptions(q=True, materialBlend=True, gl=False)[0]
		mc.polyOptions(colorMaterialChannel="none", gl=False)
		mc.polyOptions(materialBlend="overwrite", gl=False)


		# 中間オブジェクトがあるか確認
		historyList = mc.bakePartialHistory(self.targetObjMesh.fullPathName(), q=True, prePostDeformers=True) or []
		if len(historyList) > 0:
			self.hasIntermediateObject = True


		# 実行前にアクティブになっていたベースのcolorSetを保存しておく
		curColorSetList = mc.polyColorSet(q=True, currentColorSet=True)


		# colorSerがない場合生成する
		if curColorSetList == None:
			curColorSet = mc.polyColorSet(create=True, colorSet="colorSet", clamped=True, representation="RGBA")[0]
		else:
			curColorSet = curColorSetList[0]

		self.baseColorSet = curColorSet
		self.baseColorSerRep = mc.polyColorSet(q=True, currentColorSet=True, representation=True)
		self.baseColorBeforeEdit = self.targetObjMesh.getVertexColors(self.baseColorSet)

		# self.baseColorSerRepで得たベースのcolorSetの種類を元に各色を表現するためのtempのcolorSetを追加
		self.checkColorSet()


		# 現在のcolorSetの色を取得して、各色のcolorSetを編集
		# 中間オブジェクトある場合、そのcolorSet編集時にpolyColorPerVertexノードが作られる
		self.getBaseVertexColorData()


		# 中間オブジェクトある場合、念のため途中でヒストリ削除されてノードが消えた時に復活させるjobを設定
		if self.hasIntermediateObject == True:
			self.setDeleteNodeJobs()

		# 別シーンが開かれたらウィンドウを閉じるscriptJobを登録する
		self.otherSceneOpenedJob()


		if self.hasIntermediateObject == True:
			self.jobNum_attributeChange_Base = mc.scriptJob(
				attributeChange=["tmpColorSet_Base_Node.vertexColor", self.vtxColBase],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)

		else:
			self.jobNum_attributeChange_Base = mc.scriptJob(
				attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColBase],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)


	#==============================================================================================
	# .uiファイルを読み込み、ウィンドウの設定
	def setupUI(self):
		currentFilePath = os.path.dirname(__file__)

		# .uiファイルを読み込み
		loader = QUiLoader()
		uiFilePath = os.path.join(currentFilePath, 'kkDisplayVertexColorSeparatelyGUI.ui')
		self.uiFIle = loader.load(uiFilePath)
		self.setCentralWidget(self.uiFIle)

		# scriptJobのparent設定のためにオブジェクト名を設定
		self.setObjectName("kkDisplayVertexColorSeparatelyWindow")

		# ウインドウのタイトルを指定
		self.setWindowTitle("kkDisplayVertexColorSeparately")

		# ウインドウのサイズを指定
		self.resize(200, 300)

		# UI要素にシグナルを追加
		self.setSignals()

		# SelectedNameに選択オブジェクト名を表示
		self.uiFIle.lineEdit_SelObj.setText(self.targetObj.name())

		# 内蔵のpaintVertexColourツールアイコンをセットする
		self.uiFIle.btn_PaintTool.setIcon(QIcon(':/paintVertexColour.png'))

		# フレームレスにする
		self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

		# ウィンドウ自体の角を丸くする
		path = QPainterPath()
		path.addRoundedRect(self.rect(), 10, 10)
		region = QRegion(path.toFillPolygon().toPolygon())
		self.setMask(region)


	#==============================================================================================
	# このウィンドウが閉じたときの処理
	def closeEvent(self, event):
		# 他のオブジェクトを選択している可能性もあるのでそのリストを取得しておき、
		# 選択をターゲットに置き換えておく
		selList = mc.ls(sl=True)
		mc.select(self.targetObj.fullPathName(), replace=True)

		# ウィンドウのインスタンスをdeleteすることで登録したscriptJobもまとめて解除しておく
		self.deleteInstances()

		# ノード名変更のコールバックを削除
		if self.callbackID_nameChanged:
			om2.MNodeMessage.removeCallback(self.callbackID_nameChanged)
			self.callbackID_nameChanged = None


		# ターゲットオブジェクトの全colorSetリストを取得
		allColorSetList = self.targetObjMesh.getColorSetNames()

		# tmpColorSetを削除する
		if "tmpColorSet_R" in allColorSetList:
			mc.polyColorSet(delete=True, colorSet="tmpColorSet_R")

		if "tmpColorSet_G" in allColorSetList:
			mc.polyColorSet(delete=True, colorSet="tmpColorSet_G")

		if "tmpColorSet_B" in allColorSetList:
			mc.polyColorSet(delete=True, colorSet="tmpColorSet_B")

		if "tmpColorSet_A" in allColorSetList:
			mc.polyColorSet(delete=True, colorSet="tmpColorSet_A")

		# displayColorsを元に戻しておく
		mc.setAttr("%s.displayColors"%self.targetObjMesh.fullPathName(), self.attrDispColor)

		# colorMaterialChannelとmaterialBlendを元に戻しておく
		mc.polyOptions(colorMaterialChannel=self.pOption_matChl, gl=False)
		mc.polyOptions(materialBlend=self.pOption_matBld, gl=False)

		# 最後にヒストリもきれいにしておく
		historyDelete(self.targetObj.fullPathName(), False)

		# 選択を戻す
		mc.select(selList, replace=True)


	#==============================================================================================
	# フレームレスのウィンドウを動かすためにmouseEventを使用
	def mouseReleaseEvent(self, event):
		self.isDragging = False
		self.mouseCursorPos = event.pos()

	def mousePressEvent(self, event):
		self.isDragging = True
		self.mouseCursorPos = event.pos()

	def mouseMoveEvent(self, event):
		if self.isDragging == True:
			self.move(event.globalPos() - self.mouseCursorPos)


	#==============================================================================================
	# 別のシーンが開かれたときに自動でこのウィンドウを閉じる
	def otherSceneOpenedJob(self):
		self.jobNum_otherSceneOpened = mc.scriptJob(
			event=["SceneOpened", self.close],
			parent="kkDisplayVertexColorSeparatelyWindow")


	#==============================================================================================
	# ターゲットの名前が変更されたとき、表示名も変更を反映する
	def targetObjNameChangedCallback(self, node, previous, *args):
		dagNode = om2.MFnDagNode(node)
		self.uiFIle.lineEdit_SelObj.setText(dagNode.name())
		print("Target Name Changed : %s >> %s"%(previous, dagNode.name()))


	#==============================================================================================
	# シグナルの設定
	def setSignals(self):
		# colorSetの種類がRGBかRGBAじゃない場合無効化
		if self.baseColorSerRep == "RGB" or self.baseColorSerRep == "RGBA":
			self.uiFIle.btn_R.toggled.connect(self.vtxR_Toggle)
			self.uiFIle.btn_G.toggled.connect(self.vtxG_Toggle)
			self.uiFIle.btn_B.toggled.connect(self.vtxB_Toggle)
		else:
			self.uiFIle.btn_R.setEnabled(False)
			self.uiFIle.btn_G.setEnabled(False)
			self.uiFIle.btn_B.setEnabled(False)

		# colorSetの種類がRGBかRGBAじゃない場合無効化
		if self.baseColorSerRep == "RGBA" or self.baseColorSerRep == "A":
			self.uiFIle.btn_A.toggled.connect(self.vtxA_Toggle)
		else:
			self.uiFIle.btn_A.setEnabled(False)

		self.uiFIle.btn_Revert.clicked.connect(self.revert)

		self.uiFIle.btn_PaintTool.clicked.connect(self.selectPaintTool)

		self.uiFIle.btn_Close.clicked.connect(self.close)


	#==============================================================================================
	# Rのボタンがクリックされたときの処理を設定
	def vtxR_Toggle(self, checked):
		if checked:
			self.uiFIle.btn_R.setGeometry(self.btn_R_checkOnRect)

			self.uiFIle.btn_G.setChecked(False)
			self.uiFIle.btn_G.setGeometry(self.btn_G_checkOffRect)
			self.uiFIle.btn_B.setChecked(False)
			self.uiFIle.btn_B.setGeometry(self.btn_B_checkOffRect)
			self.uiFIle.btn_A.setChecked(False)
			self.uiFIle.btn_A.setGeometry(self.btn_A_checkOffRect)

			if self.hasIntermediateObject == True:
				# もしtmpColorSet_R_Nodeがない場合getBaseVertexColorDataで生成し直す
				if len(mc.ls("tmpColorSet_R_Node")) == 0:
					self.getBaseVertexColorData()

				self.jobNum_attributeChange_R = mc.scriptJob(
					attributeChange=["tmpColorSet_R_Node.vertexColor", self.vtxColSep_R],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			else:
				self.jobNum_attributeChange_R = mc.scriptJob(
					attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_R],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_R")

		else:
			if self.jobNum_attributeChange_R > 0:
				mc.scriptJob(kill=self.jobNum_attributeChange_R, force=True)
				self.jobNum_attributeChange_R = 0

			self.uiFIle.btn_R.setChecked(False)
			self.uiFIle.btn_R.setGeometry(self.btn_R_checkOffRect)

			# RGBAすべてOFFの場合ベースのcolorSetに戻す
			if self.uiFIle.btn_R.isChecked() == False and self.uiFIle.btn_G.isChecked() == False and\
				self.uiFIle.btn_B.isChecked() == False and self.uiFIle.btn_A.isChecked() == False:
				self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)


	#==============================================================================================
	# Gのボタンがクリックされたときの処理を設定
	def vtxG_Toggle(self, checked):
		if checked:
			self.uiFIle.btn_G.setGeometry(self.btn_G_checkOnRect)

			self.uiFIle.btn_R.setChecked(False)
			self.uiFIle.btn_R.setGeometry(self.btn_R_checkOffRect)
			self.uiFIle.btn_B.setChecked(False)
			self.uiFIle.btn_B.setGeometry(self.btn_B_checkOffRect)
			self.uiFIle.btn_A.setChecked(False)
			self.uiFIle.btn_A.setGeometry(self.btn_A_checkOffRect)

			if self.hasIntermediateObject == True:
				# もしtmpColorSet_G_Nodeがない場合getBaseVertexColorDataで生成し直す
				if len(mc.ls("tmpColorSet_G_Node")) == 0:
					self.getBaseVertexColorData()

				self.jobNum_attributeChange_G = mc.scriptJob(
					attributeChange=["tmpColorSet_G_Node.vertexColor", self.vtxColSep_G],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			else:
				self.jobNum_attributeChange_G = mc.scriptJob(
					attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_G],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_G")

		else:
			if self.jobNum_attributeChange_G > 0:
				mc.scriptJob(kill=self.jobNum_attributeChange_G, force=True)
				self.jobNum_attributeChange_G = 0

			self.uiFIle.btn_G.setChecked(False)
			self.uiFIle.btn_G.setGeometry(self.btn_G_checkOffRect)

			# RGBAすべてOFFの場合ベースのcolorSetに戻す
			if self.uiFIle.btn_R.isChecked() == False and self.uiFIle.btn_G.isChecked() == False and\
				self.uiFIle.btn_B.isChecked() == False and self.uiFIle.btn_A.isChecked() == False:
				self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)


	#==============================================================================================
	# Bのボタンがクリックされたときの処理を設定
	def vtxB_Toggle(self, checked):
		if checked:
			self.uiFIle.btn_B.setGeometry(self.btn_B_checkOnRect)

			self.uiFIle.btn_R.setChecked(False)
			self.uiFIle.btn_R.setGeometry(self.btn_R_checkOffRect)
			self.uiFIle.btn_G.setChecked(False)
			self.uiFIle.btn_G.setGeometry(self.btn_G_checkOffRect)
			self.uiFIle.btn_A.setChecked(False)
			self.uiFIle.btn_A.setGeometry(self.btn_A_checkOffRect)

			if self.hasIntermediateObject == True:
				# もしtmpColorSet_B_Nodeがない場合getBaseVertexColorDataで生成し直す
				if len(mc.ls("tmpColorSet_B_Node")) == 0:
					self.getBaseVertexColorData()

				self.jobNum_attributeChange_B = mc.scriptJob(
					attributeChange=["tmpColorSet_B_Node.vertexColor", self.vtxColSep_B],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			else:
				self.jobNum_attributeChange_B = mc.scriptJob(
					attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_B],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_B")

		else:
			if self.jobNum_attributeChange_B > 0:
				mc.scriptJob(kill=self.jobNum_attributeChange_B, force=True)
				self.jobNum_attributeChange_B = 0

			self.uiFIle.btn_B.setChecked(False)
			self.uiFIle.btn_B.setGeometry(self.btn_B_checkOffRect)

			# RGBAすべてOFFの場合ベースのcolorSetに戻す
			if self.uiFIle.btn_R.isChecked() == False and self.uiFIle.btn_G.isChecked() == False and\
				self.uiFIle.btn_B.isChecked() == False and self.uiFIle.btn_A.isChecked() == False:
				self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)


	#==============================================================================================
	# Aのボタンがクリックされたときの処理を設定
	def vtxA_Toggle(self, checked):
		if checked:
			self.uiFIle.btn_A.setGeometry(self.btn_A_checkOnRect)

			self.uiFIle.btn_R.setChecked(False)
			self.uiFIle.btn_R.setGeometry(self.btn_R_checkOffRect)
			self.uiFIle.btn_G.setChecked(False)
			self.uiFIle.btn_G.setGeometry(self.btn_G_checkOffRect)
			self.uiFIle.btn_B.setChecked(False)
			self.uiFIle.btn_B.setGeometry(self.btn_B_checkOffRect)

			if self.hasIntermediateObject == True:
				# もしtmpColorSet_A_Nodeがない場合getBaseVertexColorDataで生成し直す
				if len(mc.ls("tmpColorSet_A_Node")) == 0:
					self.getBaseVertexColorData()

				self.jobNum_attributeChange_A = mc.scriptJob(
					attributeChange=["tmpColorSet_A_Node.vertexColor", self.vtxColSep_A],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)

			else:
				self.jobNum_attributeChange_A = mc.scriptJob(
					attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_A],
					allChildren=True,
					parent="kkDisplayVertexColorSeparatelyWindow",
					compressUndo=True,
					runOnce=True)


			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_A")

		else:
			if self.jobNum_attributeChange_A > 0:
				mc.scriptJob(kill=self.jobNum_attributeChange_A, force=True)
				self.jobNum_attributeChange_A = 0

			self.uiFIle.btn_A.setChecked(False)
			self.uiFIle.btn_A.setGeometry(10, 205, 180, 40)

			# RGBAすべてOFFの場合ベースのcolorSetに戻す
			if self.uiFIle.btn_R.isChecked() == False and self.uiFIle.btn_G.isChecked() == False and\
				self.uiFIle.btn_B.isChecked() == False and self.uiFIle.btn_A.isChecked() == False:
				self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)


	#==============================================================================================
	# revertのボタンがクリックされたときの処理を設定
	def revert(self):
		vtxCount = self.targetObjMesh.numVertices
		if not self.targetObjVtxCount == vtxCount:
			self.targetObjVtxIdxList = xrange(vtxCount)

		self.targetObjMesh.setVertexColors(self.baseColorBeforeEdit, self.targetObjVtxIdxList)

		self.getBaseVertexColorData()


	#==============================================================================================
	# paintToolのボタンがクリックされたときの処理を設定
	def selectPaintTool(self):
		mel.eval("PaintVertexColorTool;")


	#==============================================================================================
	# tmpColorSet_RのvertexColorのattributeChangeによるscriptJobの処理を設定
	@openCloseChunk
	def vtxColSep_R(self):
		if self.uiFIle.btn_R.isChecked() == False:

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_R")
			vtxColors_tmpColorSet_R = self.targetObjMesh.getVertexColors("tmpColorSet_R")

			baseVtxColors_Edit_R = self.targetObjMesh.getVertexColors(self.baseColorSet)

			vtxCount = self.targetObjMesh.numVertices
			if not self.targetObjVtxCount == vtxCount:
				self.targetObjVtxIdxList = xrange(vtxCount)

			for x in xrange(vtxCount):
				vtxColors_tmpColorSet_R[x].r = vtxColors_tmpColorSet_R[x].r
				vtxColors_tmpColorSet_R[x].g = vtxColors_tmpColorSet_R[x].r
				vtxColors_tmpColorSet_R[x].b = vtxColors_tmpColorSet_R[x].r

				# 変更のあったRをベースに反映するために上書き
				baseVtxColors_Edit_R[x].r = vtxColors_tmpColorSet_R[x].r

			self.targetObjMesh.setVertexColors(vtxColors_tmpColorSet_R, self.targetObjVtxIdxList)

			# colorSetをベースに変更して、ベースに色を反映する
			self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)
			self.targetObjMesh.setVertexColors(baseVtxColors_Edit_R, self.targetObjVtxIdxList)

			# colorSetを戻しておく
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_R")


		if self.hasIntermediateObject == True:
			self.jobNum_attributeChange_R = mc.scriptJob(
				attributeChange=["tmpColorSet_R_Node.vertexColor", self.vtxColSep_R],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)

		else:
			self.jobNum_attributeChange_R = mc.scriptJob(
				attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_R],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)


	#==============================================================================================
	# tmpColorSet_GのvertexColorのattributeChangeによるscriptJobの処理を設定
	@openCloseChunk
	def vtxColSep_G(self):
		if self.uiFIle.btn_G.isChecked() == True:

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_G")
			vtxColors_tmpColorSet_G = self.targetObjMesh.getVertexColors("tmpColorSet_G")

			baseVtxColors_Edit_G = self.targetObjMesh.getVertexColors(self.baseColorSet)

			vtxCount = self.targetObjMesh.numVertices
			if not self.targetObjVtxCount == vtxCount:
				self.targetObjVtxIdxList = xrange(vtxCount)

			for x in xrange(vtxCount):
				vtxColors_tmpColorSet_G[x].r = vtxColors_tmpColorSet_G[x].r
				vtxColors_tmpColorSet_G[x].g = vtxColors_tmpColorSet_G[x].r
				vtxColors_tmpColorSet_G[x].b = vtxColors_tmpColorSet_G[x].r

				# 変更のあったGをベースに反映するために上書き
				baseVtxColors_Edit_G[x].g = vtxColors_tmpColorSet_G[x].g

			self.targetObjMesh.setVertexColors(vtxColors_tmpColorSet_G, self.targetObjVtxIdxList)

			# colorSetをベースに変更して、ベースに色を反映する
			self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)
			self.targetObjMesh.setVertexColors(baseVtxColors_Edit_G, self.targetObjVtxIdxList)

			# colorSetを戻しておく
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_G")


		if self.hasIntermediateObject == True:
			self.jobNum_attributeChange_G = mc.scriptJob(
				attributeChange=["tmpColorSet_G_Node.vertexColor", self.vtxColSep_G],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)

		else:
			self.jobNum_attributeChange_G = mc.scriptJob(
				attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_G],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)


	#==============================================================================================
	# tmpColorSet_BのvertexColorのattributeChangeによるscriptJobの処理を設定
	@openCloseChunk
	def vtxColSep_B(self):
		if self.uiFIle.btn_B.isChecked() == True:

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_B")
			vtxColors_tmpColorSet_B = self.targetObjMesh.getVertexColors("tmpColorSet_B")

			baseVtxColors_Edit_B = self.targetObjMesh.getVertexColors(self.baseColorSet)

			vtxCount = self.targetObjMesh.numVertices
			if not self.targetObjVtxCount == vtxCount:
				self.targetObjVtxIdxList = xrange(vtxCount)

			for x in xrange(vtxCount):
				vtxColors_tmpColorSet_B[x].r = vtxColors_tmpColorSet_B[x].r
				vtxColors_tmpColorSet_B[x].g = vtxColors_tmpColorSet_B[x].r
				vtxColors_tmpColorSet_B[x].b = vtxColors_tmpColorSet_B[x].r

				# 変更のあったBをベースに反映するために上書き
				baseVtxColors_Edit_B[x].b = vtxColors_tmpColorSet_B[x].b

			self.targetObjMesh.setVertexColors(vtxColors_tmpColorSet_B, self.targetObjVtxIdxList)

			# colorSetをベースに変更して、ベースに色を反映する
			self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)
			self.targetObjMesh.setVertexColors(baseVtxColors_Edit_B, self.targetObjVtxIdxList)

			# colorSetを戻しておく
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_B")


		if self.hasIntermediateObject == True:
			self.jobNum_attributeChange_B = mc.scriptJob(
				attributeChange=["tmpColorSet_B_Node.vertexColor", self.vtxColSep_B],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)

		else:
			self.jobNum_attributeChange_B = mc.scriptJob(
				attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_B],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)


	#==============================================================================================
	# tmpColorSet_AのvertexColorのattributeChangeによるscriptJobの処理を設定
	@openCloseChunk
	def vtxColSep_A(self):
		if self.uiFIle.btn_A.isChecked() == True:

			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_A")
			vtxColors_tmpColorSet_A = self.targetObjMesh.getVertexColors("tmpColorSet_A")

			baseVtxColors_Edit_A = self.targetObjMesh.getVertexColors(self.baseColorSet)

			vtxCount = self.targetObjMesh.numVertices
			if not self.targetObjVtxCount == vtxCount:
				self.targetObjVtxIdxList = xrange(vtxCount)

			for x in xrange(vtxCount):
				vtxColors_tmpColorSet_A[x].r = vtxColors_tmpColorSet_A[x].r
				vtxColors_tmpColorSet_A[x].g = vtxColors_tmpColorSet_A[x].r
				vtxColors_tmpColorSet_A[x].b = vtxColors_tmpColorSet_A[x].r

				# 変更のあったBをベースに反映するために上書き
				baseVtxColors_Edit_A[x].a = vtxColors_tmpColorSet_A[x].a

			self.targetObjMesh.setVertexColors(vtxColors_tmpColorSet_A, self.targetObjVtxIdxList)

			# colorSetをベースに変更して、ベースに色を反映する
			self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)
			self.targetObjMesh.setVertexColors(baseVtxColors_Edit_A, self.targetObjVtxIdxList)

			# colorSetを戻しておく
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_A")


		if self.hasIntermediateObject == True:
			self.jobNum_attributeChange_A = mc.scriptJob(
				attributeChange=["tmpColorSet_A_Node.vertexColor", self.vtxColSep_A],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)

		else:
			self.jobNum_attributeChange_A = mc.scriptJob(
				attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColSep_A],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)


	#==============================================================================================
	# ベースのvertexColorのattributeChangeによるscriptJobの処理を設定
	@openCloseChunk
	def vtxColBase(self):
		# RGBAすべてOFFの場合ベースのcolorSetに戻す
		if self.uiFIle.btn_R.isChecked() == False and self.uiFIle.btn_G.isChecked() == False and\
			self.uiFIle.btn_B.isChecked() == False and self.uiFIle.btn_A.isChecked() == False:

			self.getBaseVertexColorData()

		if self.hasIntermediateObject == True:
			self.jobNum_attributeChange_Base = mc.scriptJob(
				attributeChange=["tmpColorSet_Base_Node.vertexColor", self.vtxColBase],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)

		else:
			self.jobNum_attributeChange_Base = mc.scriptJob(
				attributeChange=["%s.colorSet"%self.targetObjMesh.fullPathName(), self.vtxColBase],
				allChildren=True,
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True,
				runOnce=True)


	#==============================================================================================
	# colorSetの存在をチェックして、なかったら生成する
	@openCloseChunk
	def checkColorSet(self):
		allColorSetList = self.targetObjMesh.getColorSetNames()

		# tmpColorSetがすでに存在するかチェックしてなければ生成
		if self.baseColorSerRep == "RGB" or self.baseColorSerRep == "RGBA":
			if not "tmpColorSet_R" in allColorSetList:
				mc.polyColorSet(create=True, colorSet="tmpColorSet_R", clamped=True, representation="RGB")

			if not "tmpColorSet_G" in allColorSetList:
				mc.polyColorSet(create=True, colorSet="tmpColorSet_G", clamped=True, representation="RGB")

			if not "tmpColorSet_B" in allColorSetList:
				mc.polyColorSet(create=True, colorSet="tmpColorSet_B", clamped=True, representation="RGB")

		if self.baseColorSerRep == "RGBA" or self.baseColorSerRep == "A":
			if not "tmpColorSet_A" in allColorSetList:
				mc.polyColorSet(create=True, colorSet="tmpColorSet_A", clamped=True, representation="RGB")


	#==============================================================================================
	# tmpColorSetNodeがヒストリの削除などでノードが消されてしまった場合のscriptJobを設定
	def setDeleteNodeJobs(self):
		if self.baseColorSerRep == "RGB" or self.baseColorSerRep == "RGBA":
			self.jobNum_nodeDeleted_R = mc.scriptJob(
				nodeDeleted=["tmpColorSet_R_Node", self.deletedNode_R],
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True)

			self.jobNum_nodeDeleted_G = mc.scriptJob(
				nodeDeleted=["tmpColorSet_G_Node", self.deletedNode_G],
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True)

			self.jobNum_nodeDeleted_B = mc.scriptJob(
				nodeDeleted=["tmpColorSet_B_Node", self.deletedNode_B],
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True)

		if self.baseColorSerRep == "RGBA" or self.baseColorSerRep == "A":
			self.jobNum_nodeDeleted_A = mc.scriptJob(
				nodeDeleted=["tmpColorSet_A_Node", self.deletedNode_A],
				parent="kkDisplayVertexColorSeparatelyWindow",
				compressUndo=True)


	#==============================================================================================
	# ベースのcolorSetに設定されている頂点カラーを取得して、それを元にtmpColorSetを生成する
	@openCloseChunk
	def getBaseVertexColorData(self):
		# 選択しているものが頂点じゃなくメッシュなので、component.getElements()じゃなく
		# MFnMesh.numVerticesによって得られる頂点数からindexListを作る
		vtxCount = self.targetObjMesh.numVertices
		if not self.targetObjVtxCount == vtxCount:
			self.targetObjVtxIdxList = xrange(vtxCount)

		baseVtxColors = self.targetObjMesh.getVertexColors(self.baseColorSet)

		# ベースのcolorSetの種類がRGBかRGBAの場合のみRGBの処理を行う
		if self.baseColorSerRep == "RGB" or self.baseColorSerRep == "RGBA":

			# 一旦baseVtxColorsのMColorArrayをコピーしたリストを作っておく
			baseVtxColors_R = baseVtxColors[:]
			baseVtxColors_G = baseVtxColors[:]
			baseVtxColors_B = baseVtxColors[:]

			# tmpColorSet_RにbaseColorSetのRedを適用する
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_R")
			for x in range(vtxCount):
				baseVtxColors_R[x].r = baseVtxColors_R[x].r
				baseVtxColors_R[x].g = baseVtxColors_R[x].r
				baseVtxColors_R[x].b = baseVtxColors_R[x].r
			self.targetObjMesh.setVertexColors(baseVtxColors_R, self.targetObjVtxIdxList)


			# tmpColorSet_GにbaseColorSetのGreenを適用する
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_G")
			for y in xrange(vtxCount):
				baseVtxColors_G[y].r = baseVtxColors_G[y].g
				baseVtxColors_G[y].g = baseVtxColors_G[y].g
				baseVtxColors_G[y].b = baseVtxColors_G[y].g
			self.targetObjMesh.setVertexColors(baseVtxColors_G, self.targetObjVtxIdxList)


			# tmpColorSet_BにbaseColorSetのBlueを適用する
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_B")
			for z in range(vtxCount):
				baseVtxColors_B[z].r = baseVtxColors_B[z].b
				baseVtxColors_B[z].g = baseVtxColors_B[z].b
				baseVtxColors_B[z].b = baseVtxColors_B[z].b
			self.targetObjMesh.setVertexColors(baseVtxColors_B, self.targetObjVtxIdxList)


		# ベースのcolorSetの種類がRGBAかAの場合のみAlphaの処理を行う
		if self.baseColorSerRep == "RGBA" or self.baseColorSerRep == "A":

			# 一旦baseVtxColorsのMColorArrayをコピーしたリストを作っておく
			baseVtxColors_A = baseVtxColors[:]

			# tmpColorSet_AにbaseColorSetのAlphaを適用する
			self.targetObjMesh.setCurrentColorSetName("tmpColorSet_A")
			for w in range(vtxCount):
				baseVtxColors_A[w].r = baseVtxColors_A[w].a
				baseVtxColors_A[w].g = baseVtxColors_A[w].a
				baseVtxColors_A[w].b = baseVtxColors_A[w].a
			self.targetObjMesh.setVertexColors(baseVtxColors_A, self.targetObjVtxIdxList)

		# colorSetをベースに戻しておく
		self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)


		if self.hasIntermediateObject == True:
			# tmpColorSet_Base_Nodeがない場合、baseColor変更感知用のpolyColorPerVertexを作っておく
			if len(mc.ls("tmpColorSet_Base_Node", type="polyColorPerVertex")) == 0:
				self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)
				self.targetObjMesh.setVertexColors(baseVtxColors, self.targetObjVtxIdxList)


			polyColorVertexNodeList = mc.ls(type="polyColorPerVertex")

			for polyColorVertexNode in polyColorVertexNodeList:
				colorSetName = mc.getAttr("%s.colorSetName"%polyColorVertexNode)

				if "tmpColorSet_R" in colorSetName:
					mc.rename(polyColorVertexNode, "tmpColorSet_R_Node")

				elif "tmpColorSet_G" in colorSetName:
					mc.rename(polyColorVertexNode, "tmpColorSet_G_Node")

				elif "tmpColorSet_B" in colorSetName:
					mc.rename(polyColorVertexNode, "tmpColorSet_B_Node")

				elif "tmpColorSet_A" in colorSetName:
					mc.rename(polyColorVertexNode, "tmpColorSet_A_Node")

				elif self.baseColorSet in colorSetName:
					mc.rename(polyColorVertexNode, "tmpColorSet_Base_Node")





	#==============================================================================================
	# 各tmpColorSetに設定していたColorを取得して、ベースのcolorSetにセットする
	@openCloseChunk
	def mergeColorSet(self):
		if self.baseColorSerRep == "RGB" or self.baseColorSerRep == "RGBA":
			vtxColors_R = self.targetObjMesh.getVertexColors("tmpColorSet_R")
			vtxColors_G = self.targetObjMesh.getVertexColors("tmpColorSet_G")
			vtxColors_B = self.targetObjMesh.getVertexColors("tmpColorSet_B")

		if self.baseColorSerRep == "RGBA" or self.baseColorSerRep == "A":
			vtxColors_A = self.targetObjMesh.getVertexColors("tmpColorSet_A")

		vtxColors_Result = self.targetObjMesh.getVertexColors(self.baseColorSet)
		self.targetObjMesh.setCurrentColorSetName(self.baseColorSet)

		vtxCount = self.targetObjMesh.numVertices
		# もし頂点数が変わっていたらvertexIndexListを作り直す
		if not self.targetObjVtxCount == vtxCount:
			self.targetObjVtxIdxList = xrange(vtxCount)


		if self.baseColorSerRep == "RGB":
			for x in xrange(vtxCount):
				vtxColors_Result[x].r = vtxColors_R[x].r
				vtxColors_Result[x].g = vtxColors_G[x].r
				vtxColors_Result[x].b = vtxColors_B[x].r


		elif self.baseColorSerRep == "A":
			for y in xrange(vtxCount):
				vtxColors_Result[y].r = 0
				vtxColors_Result[y].g = 0
				vtxColors_Result[y].b = 0
				vtxColors_Result[y].a = vtxColors_A[y].r

		else: # self.baseColorSerRep == "RGBA"
			for z in xrange(vtxCount):
				vtxColors_Result[z].r = vtxColors_R[z].r
				vtxColors_Result[z].g = vtxColors_G[z].r
				vtxColors_Result[z].b = vtxColors_B[z].r
				vtxColors_Result[z].a = vtxColors_A[z].r

		self.targetObjMesh.setVertexColors(vtxColors_Result, self.targetObjVtxIdxList)


	#==============================================================================================
	# 各tmpColorSetNodeが消えてしまったら生成し直す
	def deletedNode_R(self):
		self.getBaseVertexColorData()

	def deletedNode_G(self):
		self.getBaseVertexColorData()

	def deletedNode_B(self):
		self.getBaseVertexColorData()

	def deletedNode_A(self):
		self.getBaseVertexColorData()


	#==============================================================================================
	# このウィンドウが存在したら消す
	def deleteInstances(self):
		for obj in getMayaWindow().children():
			if obj.objectName() == "kkDisplayVertexColorSeparatelyWindow":
				obj.setParent(None)
				obj.deleteLater()


#----------------------------------------------------------------------------------------------------------------------
# デフォーマがついているとコンポーネントエディタから頂点カラーを変更した際に
# ヒストリを削除しないときちんと反映されずscriptJobが反応しないための対処
def historyDelete(targetObj, isStart):
	if isStart == True:
		dialogMessage = ""
		lang = mc.about(uiLanguage=True)
		if lang == "ja_JP":
			dialogMessage = "実行前に「デフォーマ以外のヒストリ」削除を行いますがよろしいですか？"
		else:
			dialogMessage = 'Do you delete "Non-Deformer History"\nfor the selected object before execution?'

		# ヒストリを削除してよいかの確認ダイアログ表示
		selDialog = mc.confirmDialog(
			title='kkDisplayVertexColorSeparately_Check',
			message=dialogMessage,
			button=['Yes','No'],
			defaultButton='Yes',
			cancelButton='No',
			dismissString='No')

		if selDialog == "No":
			mc.warning("kkDisplayVertexColorSeparately is Canceled."),
			return False

	# デフォーマ以外のヒストリの削除実行
	mc.bakePartialHistory(targetObj, prePostDeformers=True)

	return True


#----------------------------------------------------------------------------------------------------------------------

def getMayaWindow():
	mainWinPtr = omUI.MQtUtil.mainWindow()
	return wrapInstance(long(mainWinPtr), QMainWindow)


#----------------------------------------------------------------------------------------------------------------------

def main():
	selList = mc.ls(sl=True, type="transform")

	if len(selList) == 0:
		mc.warning("No Select..."),
		return

	selMeshList = mc.listRelatives(selList[0], shapes=True, type="mesh")
	if len(selMeshList) == 0:
		mc.warning("Mesh is not selected..."),
		return

	# 選択を１つだけに絞っておく
	mc.select(selList[0], replace=True)

	isHistoryDeleted = historyDelete(selList[0], True)

	if isHistoryDeleted == True:
		app = QApplication.instance()
		dispVtxColSepWindow = kkDisplayVertexColorSeparatelyWindow()
		dispVtxColSepWindow.show()
		sys.exit()
		app.exec_()


if __name__ == '__main__':
	main()
