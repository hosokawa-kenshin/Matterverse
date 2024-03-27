# beacon_mediator
各人が持つ Beacon の BLE の受信，Beacon と デバイス間の距離の推定を行い，Matter を用いて送信する Mediator．ボタンを押すと Aggregator とコミッショニングを開始する．

## 使い方
1. app_main.cppにて，接続する Aggregator の Pincode を指定する．(デフォルトでは20202021)
    ```cpp
    uint64_t pincode = static_cast<uint64_t>(20202021);
    ```
2. 接続するネットワークの設定を行う．
    ```bash
    cd beacon_mediator
    idf.py menuconfig
    ```
    Component config --> CHIP Device Layer --> WiFi Station Options にて Default WiFi SSID，Default WiFi Password を設定する．
3. ビルド，書き込みを行う．
    ```bash
    idf.py build
    idf.py flash
    ```