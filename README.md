# Matterverse
本プロジェクトは，工場向け IoT システムのようなベンダ依存の強い IoT システムに Matter を適用することで IoT システムを民主化する試みである．
相互運用性の問題を抱える IoT システムに Matter を適用することでデバイス間の相互運用性が高くなり，異なるベンダのシステムの統合が可能になると考えられる．現在は，BLEのRSSIを用いた位置推定システムの通信規格を Matter に置き換え，実装する取り組みを行っている．

"Matterverse"は，"Matter"と"Universe" を組み合わせた造語である．
この名前は，通信規格である"Matter"と世界を表す"Universe"を組み合わせたものである．
## Examples
### beacon_aggregator
各人が持つ Beacon に関する情報を Matter で受信し，Beacon の位置を推定する AggregatorのESP32実装．
### beacon_mediator
各人が持つ Beacon の BLE の受信，Beacon と デバイス間の距離の推定を行い，Matter を用いて送信する MediatorのESP32実装．
