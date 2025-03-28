``` mermaid
erDiagram
  Device {
    int NodeID PK
  }

  Endpoint {
    int ID PK
    int DeviceID FK
    int DeviceTypeID FK
  }

  DeviceType {
    int ID PK
  }

  Cluster {
    int ID PK
    int EndpointID FK
    string Name
  }

  Attribute {
    int ID PK
    int ClusterID PK
    string Name
    string DataType
  }

  AttributeValue {
    int ID PK
    int AttributeID PK
    int DeviceID PK
    string Value
    datetime Timestamp
  }

  Device ||--|{ Endpoint : has
  DeviceType ||--|{ Endpoint : has
  Endpoint ||--|{ Cluster : has
  Cluster ||--|{ Attribute : has
  Attribute ||--|{ AttributeValue : has
  Device ||--|{ AttributeValue : stores
  ```