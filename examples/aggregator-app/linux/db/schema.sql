CREATE TABLE Beacon(
  ID int primary key,
  UUID char(36),
  Major int,
  Minor int,
  TxPower int,
  Description varchar(255)
);

CREATE TABLE Mediator(
  ID int primary key,
  UID varchar(20),
  Room varchar(10),
  X_Coordinate double,
  Y_Coordinate double,
  Z_Coordinate double,
  Description varchar(255)
);

CREATE TABLE Signal(
  ID int primary key,
  BeaconUUID char(36),
  MediatorUID varchar(20),
  Distance double,
  Timestamp datetime
);
