``` mermaid
erDiagram
  Beacon {
    int ID PK
    char(36) UUID
    int Major
    int Minor
    int TxPower
    varchar(255) Description
  }

  Mediator {
    int ID PK
    varchar(20) UID
    varchar(20) Room
    double X_Coordinate
    double Y_Coordinate
    double Z_Coordinate
    varchar(255) Description
  }

  Signal {
    int ID PK
    char(36) BeaconUUID
    varchar(20) MediatorUID
    double Distance
    datetime Timestamp
  }
  ```