# Matterverse
本システムは，スマートホームの標準規格 Matter を活用したIoTシステムである．
Matter は，異なるメーカのデバイスが互いに連携できる標準化された基盤を提供することを目的として 2022 年に策定された．工場向け IoT システムのような相互運用性の問題を抱える IoT システムに Matter を適用することでデバイス間の相互運用性が高くなり，異なるベンダのシステムの統合が可能になる．

"Matterverse"は，"Matter"と"Universe" を組み合わせた造語である．
この名前は，通信規格である"Matter"と世界を表す"Universe"を組み合わせたものである．

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
## Examples
### beacon_aggregator
各人が持つ Beacon の BLE 情報を Matter で受信し，Beacon の位置を推定する Aggregator．
### beacon_mediator
各人が持つ Beacon の BLE の受信，Beacon と デバイス間の距離の推定を行い，Matter を用いて送信する Mediator．