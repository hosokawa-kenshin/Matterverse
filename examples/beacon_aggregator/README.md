# beacon_aggregator
各人が持つ Beacon の BLE 情報を Matter で受信し，Beacon の位置を推定する Aggregator．ボタンを押すと Mediator とコミッショニングを開始する．

## 使い方
1. 接続するネットワークの設定を行う．
    ```bash
    cd beacon_mediator
    idf.py menuconfig
    ```
    Component config --> CHIP Device Layer --> WiFi Station Options にて Default WiFi SSID，Default WiFi Password を設定する．
2. ビルド，書き込みを行う．
    ```bash
    idf.py build
    idf.py flash
    ```