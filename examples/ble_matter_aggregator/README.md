# BLE Matter Aggregator
A Linux-based Aggregator implementation that receives BLE data from personal Beacons through Matter and performs Beacon position estimation.

## Setup
-   Install tool chain

    ```bash
    sudo apt-get install git gcc g++ python pkg-config libssl-dev libdbus-1-dev libglib2.0-dev ninja-build python3-venv python3-dev unzip
    ```

-   Build the example application:

    ```bash
    git clone https://github.com/hosokawa-kenshin/Matterverse.git --recursive
    cd Matterverse/sdk
    source scripts/bootstrap.sh
    cd ..
    cp examples/ble_matter_aggregator/ sdk/examples/.
    cd sdk/examples/ble_matter_aggregator/linux
    gn gen out
    ninja -C out
    ```

-   To delete generated executable, libraries and object files use:

    ```sh
    cd Matterverse/sdk/examples/ble_matter_aggregator/linux
    rm -rf out/
    ```

# Schema
