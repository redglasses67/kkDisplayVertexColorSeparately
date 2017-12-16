# kkDisplayVertexColorSeparately

Maya / Python  
頂点カラーをRGBA別々に確認・編集するスクリプト    
![使い方画像](https://github.com/redglasses67/kkDisplayVertexColorSeparately/blob/master/kkDisplayVertexColorSeparately_ColorChange.gif)
***

## 使い方
 GitHubのページの「Clone or download」ボタンからZipファイルをDLしてもらい、  
それを展開してもらうとscriptsフォルダの中に

・**kkDisplayVertexColorSeparately.mel** ファイル  
・**kkDisplayVertexColorSeparately** フォルダ

の2つがあります。

 

kkDisplayVertexColorSeparatelyフォルダの方にはPythonのスクリプトとQtDesignerで作ったuiファイルが入っています。

これらをMayaのSCRIPT_PATHやPYTHON_PATHが通った場所にコピーして下さい。

※よく分からない方は C:\Users\ユーザー名\Documents\maya\2017\scripts
（日本語版は C:\Users\ユーザー名\Documents\maya\2017\ja_JP\scripts） などにコピーして下さい。


melファイルの方はなくてもいいんですが、実行を簡単にするために用意しました。

このmelに処理が書いてあるpythonファイルの実行コードが書いてあるので、

melで実行される場合は  
`kkDisplayVertexColorSeparately;`

 
Pythonで実行される場合は  
`from kkDisplayVertexColorSeparately import kkDisplayVertexColorSeparately`
`kkDisplayVertexColorSeparately.main() `

***
## 更新履歴
2017.12.17 リリース
