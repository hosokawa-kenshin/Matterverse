# BLE Matter Mediator
The BLE Matter Mediator is a component that receives BLE signals from Beacon devices, estimates the distance to each Beacon, and forwards the resulting information to upper-layer nodes using the Matter protocol.
It serves as a bridge between BLE-based sensing and Matter-based IoT systems, enabling Beacon-driven location awareness within a Matter network.

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
    cp examples/ble_matter_mediator/ sdk/examples/.
    cd sdk/examples/ble_matter_mediator/linux
    gn gen out
    ninja -C out
    ```

-   To delete generated executable, libraries and object files use:

    ```sh
    cd Matterverse/sdk/examples/ble_matter_mediator/linux
    rm -rf out/
    ```

## Message Format
The Mediator writes Beacon-related information to the LogEntry attribute of the Location Detector Cluster defined in Matter. These log entries are consumed by Aggregator nodes to perform Beacon position estimation.

Each entry written to the LogEntry attribute is represented as a single string with the following format:
```
BeaconUUID:Distance:MediatorUID
```
- BeaconUUID:
The UUID of the detected BLE Beacon.

- Distance:
The estimated distance between the Beacon and the Mediator, derived from BLE signal measurements.

- MediatorUID:
A unique identifier assigned to the Mediator device that generated the entry.

This structured format allows Aggregators to correlate distance measurements from multiple Mediators and compute the estimated positions of Beacons.