# beacon_aggregator
各人が持つ Beacon の BLE 情報を Matter で受信し，Beacon の位置を推定する AggregatorのESP32実装．ボタンを押すと Mediator とコミッショニングを開始する．
## Requirements
esp-idf v4.4.4
esp-matter v1.0
Python 3.x
## Setup
1. 前提環境をセットアップする．
    ```bash
    sudo apt-get install git wget flex bison gperf python3 python3-pip python3-venv cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0
    ```
2. esp-idf をインストールする
    ```
    git clone --recursive https://github.com/espressif/esp-idf.git -b v4.4.4
    cd esp-idf
    ./install.sh
    source export.sh
    cd ..
    ```
3. esp-matter をインストールする
    ```
    git clone --recursive git@github.com:hosokawa-kenshin/esp-matter.git
    cd esp-matter
    ./install.sh
    source export.sh
    cd ..
    ```
## 使い方
1. 書き込むターゲットを指定する．
    ```bash
    export ESP_MATTER_DEVICE_PATH=$(pwd)/device/m5stampc3 && idf.py set-target esp32c3
    ```
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