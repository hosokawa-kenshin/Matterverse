/*
 *
 *    Copyright (c) 2021 Project CHIP Authors
 *    All rights reserved.
 *
 *    Licensed under the Apache License, Version 2.0 (the "License");
 *    you may not use this file except in compliance with the License.
 *    You may obtain a copy of the License at
 *
 *        http://www.apache.org/licenses/LICENSE-2.0
 *
 *    Unless required by applicable law or agreed to in writing, software
 *    distributed under the License is distributed on an "AS IS" BASIS,
 *    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *    See the License for the specific language governing permisconst EmberAfDeviceType gBridgedEntityLocationDeviceTypes[] = { {
DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gBridgedTempSensorDeviceTypes[] = { { DEVICE_TYPE_TEMP_SENSOR, DEVICE_VERSION_DEFAULT },
                                                            { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };and
 *    limitations under the License.
 */

#include <AppMain.h>
#include <platform/CHIPDeviceLayer.h>
#include <platform/PlatformManager.h>

#include <app-common/zap-generated/ids/Attributes.h>
#include <app-common/zap-generated/ids/Clusters.h>
#include <app/AttributeAccessInterfaceRegistry.h>
#include <app/ConcreteAttributePath.h>
#include <app/EventLogging.h>
#include <app/reporting/reporting.h>
#include <app/util/af-types.h>
#include <app/util/attribute-storage.h>
#include <app/util/endpoint-config-api.h>
#include <app/util/util.h>
#include <credentials/DeviceAttestationCredsProvider.h>
#include <credentials/examples/DeviceAttestationCredsExample.h>
#include <lib/core/CHIPError.h>
#include <lib/support/CHIPMem.h>
#include <lib/support/ZclString.h>
#include <platform/CommissionableDataProvider.h>
#include <setup_payload/QRCodeSetupPayloadGenerator.h>
#include <setup_payload/SetupPayload.h>

#include <pthread.h>
#include <sys/ioctl.h>

#include "CommissionableInit.h"
#include "Device.h"
#include "main.h"
#include <app/server/Server.h>

#include <cassert>
#include <iostream>
#include <string>
#include <vector>

using namespace chip;
using namespace chip::app;
using namespace chip::Credentials;
using namespace chip::Inet;
using namespace chip::Transport;
using namespace chip::DeviceLayer;
using namespace chip::app::Clusters;

namespace {

const int kNodeLabelSize         = 32;
const int kUniqueIdSize          = 32;
const int kEntityLocationMaxSize = 64;
// Current ZCL implementation of Struct uses a max-size array of 254 bytes
const int kDescriptorAttributeArraySize = 254;

EndpointId gCurrentEndpointId;
EndpointId gFirstDynamicEndpointId;
// Power source is on the same endpoint as the composed device
Device * gDevices[CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT + 1];

const int16_t minMeasuredValue     = -27315;
const int16_t maxMeasuredValue     = 32766;
const int16_t initialMeasuredValue = 100;

// Device types for dynamic endpoints: TODO Need a generated file from ZAP to define these!
// (taken from matter-devices.xml)
#define DEVICE_TYPE_BRIDGED_NODE 0x0013
// (taken from lo-devices.xml)
// Device Version for dynamic endpoints:
#define DEVICE_VERSION_DEFAULT 1

// ---------------------------------------------------------------------------
//
// ENTITY LOCATION ENDPOINT: contains the following clusters:
//   - ENTITY LOCATION
//   - Descriptor
//   - Bridged Device Basic Information

DECLARE_DYNAMIC_ATTRIBUTE_LIST_BEGIN(entityLocationAttrs)
DECLARE_DYNAMIC_ATTRIBUTE(EntityLocation::Attributes::Id::Id, CHAR_STRING, kEntityLocationMaxSize, ZAP_ATTRIBUTE_MASK(WRITABLE)),
    DECLARE_DYNAMIC_ATTRIBUTE(EntityLocation::Attributes::Location::Id, CHAR_STRING, kEntityLocationMaxSize,
                              ZAP_ATTRIBUTE_MASK(WRITABLE)),
    DECLARE_DYNAMIC_ATTRIBUTE_LIST_END();

// Declare Descriptor cluster attributes
DECLARE_DYNAMIC_ATTRIBUTE_LIST_BEGIN(descriptorAttrs)
DECLARE_DYNAMIC_ATTRIBUTE(Descriptor::Attributes::DeviceTypeList::Id, ARRAY, kDescriptorAttributeArraySize, 0), /* device list */
    DECLARE_DYNAMIC_ATTRIBUTE(Descriptor::Attributes::ServerList::Id, ARRAY, kDescriptorAttributeArraySize, 0), /* server list */
    DECLARE_DYNAMIC_ATTRIBUTE(Descriptor::Attributes::ClientList::Id, ARRAY, kDescriptorAttributeArraySize, 0), /* client list */
    DECLARE_DYNAMIC_ATTRIBUTE(Descriptor::Attributes::PartsList::Id, ARRAY, kDescriptorAttributeArraySize, 0),  /* parts list */
    DECLARE_DYNAMIC_ATTRIBUTE_LIST_END();

// Declare Bridged Device Basic Information cluster attributes
DECLARE_DYNAMIC_ATTRIBUTE_LIST_BEGIN(bridgedDeviceBasicAttrs)
DECLARE_DYNAMIC_ATTRIBUTE(BridgedDeviceBasicInformation::Attributes::NodeLabel::Id, CHAR_STRING, kNodeLabelSize, 0), /* NodeLabel */
    DECLARE_DYNAMIC_ATTRIBUTE(BridgedDeviceBasicInformation::Attributes::Reachable::Id, BOOLEAN, 1, 0),              /* Reachable */
    DECLARE_DYNAMIC_ATTRIBUTE(BridgedDeviceBasicInformation::Attributes::UniqueID::Id, CHAR_STRING, kUniqueIdSize, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(BridgedDeviceBasicInformation::Attributes::FeatureMap::Id, BITMAP32, 4, 0), /* feature map */
    DECLARE_DYNAMIC_ATTRIBUTE_LIST_END();

DECLARE_DYNAMIC_CLUSTER_LIST_BEGIN(bridgedEntityLocationClusters)
DECLARE_DYNAMIC_CLUSTER(EntityLocation::Id, entityLocationAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(Descriptor::Id, descriptorAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(BridgedDeviceBasicInformation::Id, bridgedDeviceBasicAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr,
                            nullptr) DECLARE_DYNAMIC_CLUSTER_LIST_END;

// Declare Bridged Light endpoint
DECLARE_DYNAMIC_ENDPOINT(bridgedEntityLoEndpoint, bridgedEntityLocationClusters);
DataVersion gPerson1DataVersions[ArraySize(bridgedEntityLocationClusters)];
DataVersion gPerson2DataVersions[ArraySize(bridgedEntityLocationClusters)];
DataVersion gPerson3DataVersions[ArraySize(bridgedEntityLocationClusters)];
DataVersion gPerson4DataVersions[ArraySize(bridgedEntityLocationClusters)];

DeviceEntityLocation Person1("Person 1", "Unknown", "person_001", "Unknown Location");
DeviceEntityLocation Person2("Person 2", "Unknown", "person_002", "Unknown Location");
DeviceEntityLocation Person3("Person 3", "Unknown", "person_003", "Unknown Location");
DeviceEntityLocation Person4("Person 4", "Unknown", "person_004", "Unknown Location");

// REVISION DEFINITIONS:
// =================================================================================

#define ZCL_DESCRIPTOR_CLUSTER_REVISION (1u)
#define ZCL_BRIDGED_DEVICE_BASIC_INFORMATION_CLUSTER_REVISION (2u)
#define ZCL_BRIDGED_DEVICE_BASIC_INFORMATION_FEATURE_MAP (0u)
#define ZCL_FIXED_LABEL_CLUSTER_REVISION (1u)
#define ZCL_ON_OFF_CLUSTER_REVISION (4u)
#define ZCL_TEMPERATURE_SENSOR_CLUSTER_REVISION (1u)
#define ZCL_TEMPERATURE_SENSOR_FEATURE_MAP (0u)
#define ZCL_POWER_SOURCE_CLUSTER_REVISION (2u)
#define ZCL_ENTITY_LOCATION_CLUSTER_REVISION (1u)

// ---------------------------------------------------------------------------

int AddDeviceEndpoint(Device * dev, EmberAfEndpointType * ep, const Span<const EmberAfDeviceType> & deviceTypeList,
                      const Span<DataVersion> & dataVersionStorage, chip::EndpointId parentEndpointId = chip::kInvalidEndpointId)
{
    uint8_t index = 0;
    while (index < CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT)
    {
        if (nullptr == gDevices[index])
        {
            gDevices[index] = dev;
            CHIP_ERROR err;
            while (true)
            {
                // Todo: Update this to schedule the work rather than use this lock
                DeviceLayer::StackLock lock;
                dev->SetEndpointId(gCurrentEndpointId);
                dev->SetParentEndpointId(parentEndpointId);
                err =
                    emberAfSetDynamicEndpoint(index, gCurrentEndpointId, ep, dataVersionStorage, deviceTypeList, parentEndpointId);
                if (err == CHIP_NO_ERROR)
                {
                    ChipLogProgress(DeviceLayer, "Added device %s to dynamic endpoint %d (index=%d)", dev->GetName(),
                                    gCurrentEndpointId, index);

                    if (dev->GetUniqueId()[0] == '\0')
                    {
                        dev->GenerateUniqueId();
                    }

                    return index;
                }
                if (err != CHIP_ERROR_ENDPOINT_EXISTS)
                {
                    gDevices[index] = nullptr;
                    return -1;
                }
                // Handle wrap condition
                if (++gCurrentEndpointId < gFirstDynamicEndpointId)
                {
                    gCurrentEndpointId = gFirstDynamicEndpointId;
                }
            }
        }
        index++;
    }
    ChipLogProgress(DeviceLayer, "Failed to add dynamic endpoint: No endpoints available!");
    return -1;
}

void CallReportingCallback(intptr_t closure)
{
    auto path = reinterpret_cast<app::ConcreteAttributePath *>(closure);
    MatterReportingAttributeChangeCallback(*path);
    Platform::Delete(path);
}

void ScheduleReportingCallback(Device * dev, ClusterId cluster, AttributeId attribute)
{
    auto * path = Platform::New<app::ConcreteAttributePath>(dev->GetEndpointId(), cluster, attribute);
    PlatformMgr().ScheduleWork(CallReportingCallback, reinterpret_cast<intptr_t>(path));
}

} // namespace

std::vector<EndpointListInfo> GetEndpointListInfo(chip::EndpointId parentId)
{
    std::vector<EndpointListInfo> infoList;
    return infoList;
}

std::vector<Action *> GetActionListInfo(chip::EndpointId parentId)
{
    std::vector<Action *> actionList;
    return actionList;
}

bool emberAfActionsClusterInstantActionCallback(app::CommandHandler * commandObj, const app::ConcreteCommandPath & commandPath,
                                                const Actions::Commands::InstantAction::DecodableType & commandData)
{
    commandObj->AddStatus(commandPath, Protocols::InteractionModel::Status::NotFound);
    return true;
}

void HandleDeviceStatusChanged(Device * dev, Device::Changed_t itemChangedMask)
{
    if (itemChangedMask & Device::kChanged_Reachable)
    {
        ScheduleReportingCallback(dev, BridgedDeviceBasicInformation::Id, BridgedDeviceBasicInformation::Attributes::Reachable::Id);
    }

    if (itemChangedMask & Device::kChanged_Name)
    {
        ScheduleReportingCallback(dev, BridgedDeviceBasicInformation::Id, BridgedDeviceBasicInformation::Attributes::NodeLabel::Id);
    }
}

void HandleDeviceEntityLocationStatusChanged(DeviceEntityLocation * dev, DeviceEntityLocation::Changed_t itemChangedMask)
{
    if (itemChangedMask &
        (DeviceEntityLocation::kChanged_Reachable | DeviceEntityLocation::kChanged_Name | DeviceEntityLocation::kChanged_Location))
    {
        HandleDeviceStatusChanged(static_cast<Device *>(dev), (Device::Changed_t) itemChangedMask);
    }

    if (itemChangedMask & DeviceEntityLocation::kChanged_ID)
    {
        ScheduleReportingCallback(dev, EntityLocation::Id, EntityLocation::Attributes::Id::Id);
    }

    if (itemChangedMask & DeviceEntityLocation::kChanged_LocationAttribute)
    {
        ScheduleReportingCallback(dev, EntityLocation::Id, EntityLocation::Attributes::Location::Id);
    }
}

void HandleDevicePowerSourceStatusChanged(DevicePowerSource * dev, DevicePowerSource::Changed_t itemChangedMask)
{
    using namespace app::Clusters;
    if (itemChangedMask &
        (DevicePowerSource::kChanged_Reachable | DevicePowerSource::kChanged_Name | DevicePowerSource::kChanged_Location))
    {
        HandleDeviceStatusChanged(static_cast<Device *>(dev), (Device::Changed_t) itemChangedMask);
    }

    if (itemChangedMask & DevicePowerSource::kChanged_BatLevel)
    {
        MatterReportingAttributeChangeCallback(dev->GetEndpointId(), PowerSource::Id, PowerSource::Attributes::BatChargeLevel::Id);
    }

    if (itemChangedMask & DevicePowerSource::kChanged_Description)
    {
        MatterReportingAttributeChangeCallback(dev->GetEndpointId(), PowerSource::Id, PowerSource::Attributes::Description::Id);
    }
    if (itemChangedMask & DevicePowerSource::kChanged_EndpointList)
    {
        MatterReportingAttributeChangeCallback(dev->GetEndpointId(), PowerSource::Id, PowerSource::Attributes::EndpointList::Id);
    }
}

void HandleDeviceTempSensorStatusChanged(DeviceTempSensor * dev, DeviceTempSensor::Changed_t itemChangedMask)
{
    if (itemChangedMask &
        (DeviceTempSensor::kChanged_Reachable | DeviceTempSensor::kChanged_Name | DeviceTempSensor::kChanged_Location))
    {
        HandleDeviceStatusChanged(static_cast<Device *>(dev), (Device::Changed_t) itemChangedMask);
    }
    if (itemChangedMask & DeviceTempSensor::kChanged_MeasurementValue)
    {
        ScheduleReportingCallback(dev, TemperatureMeasurement::Id, TemperatureMeasurement::Attributes::MeasuredValue::Id);
    }
}

Protocols::InteractionModel::Status HandleReadBridgedDeviceBasicAttribute(Device * dev, chip::AttributeId attributeId,
                                                                          uint8_t * buffer, uint16_t maxReadLength)
{
    using namespace BridgedDeviceBasicInformation::Attributes;

    ChipLogProgress(DeviceLayer, "HandleReadBridgedDeviceBasicAttribute: attrId=%d, maxReadLength=%d", attributeId, maxReadLength);

    if ((attributeId == Reachable::Id) && (maxReadLength == 1))
    {
        *buffer = dev->IsReachable() ? 1 : 0;
    }
    else if ((attributeId == NodeLabel::Id) && (maxReadLength == 32))
    {
        MutableByteSpan zclNameSpan(buffer, maxReadLength);
        MakeZclCharString(zclNameSpan, dev->GetName());
    }
    else if ((attributeId == UniqueID::Id) && (maxReadLength == 32))
    {
        MutableByteSpan zclUniqueIdSpan(buffer, maxReadLength);
        MakeZclCharString(zclUniqueIdSpan, dev->GetUniqueId());
    }
    else if ((attributeId == ClusterRevision::Id) && (maxReadLength == 2))
    {
        uint16_t rev = ZCL_BRIDGED_DEVICE_BASIC_INFORMATION_CLUSTER_REVISION;
        memcpy(buffer, &rev, sizeof(rev));
    }
    else if ((attributeId == FeatureMap::Id) && (maxReadLength == 4))
    {
        uint32_t featureMap = ZCL_BRIDGED_DEVICE_BASIC_INFORMATION_FEATURE_MAP;
        memcpy(buffer, &featureMap, sizeof(featureMap));
    }
    else
    {
        return Protocols::InteractionModel::Status::Failure;
    }

    return Protocols::InteractionModel::Status::Success;
}

Protocols::InteractionModel::Status HandleReadEntityLocationAttribute(DeviceEntityLocation * dev, chip::AttributeId attributeId,
                                                                      uint8_t * buffer, uint16_t maxReadLength)
{
    ChipLogProgress(DeviceLayer, "HandleReadEntityLocationAttribute: attrId=%d, maxReadLength=%d", attributeId, maxReadLength);

    if ((attributeId == EntityLocation::Attributes::Id::Id) && (maxReadLength == kEntityLocationMaxSize))
    {
        MutableByteSpan zclIdSpan(buffer, maxReadLength);
        MakeZclCharString(zclIdSpan, dev->GetEntityID().c_str());
    }
    else if ((attributeId == EntityLocation::Attributes::Location::Id) && (maxReadLength == kEntityLocationMaxSize))
    {
        MutableByteSpan zclLocationSpan(buffer, maxReadLength);
        MakeZclCharString(zclLocationSpan, dev->GetEntityLocation().c_str());
    }
    else if ((attributeId == EntityLocation::Attributes::ClusterRevision::Id) && (maxReadLength == 2))
    {
        uint16_t rev = ZCL_ENTITY_LOCATION_CLUSTER_REVISION;
        memcpy(buffer, &rev, sizeof(rev));
    }
    else
    {
        return Protocols::InteractionModel::Status::Failure;
    }

    return Protocols::InteractionModel::Status::Success;
}

Protocols::InteractionModel::Status HandleWriteEntityLocationAttribute(DeviceEntityLocation * dev, chip::AttributeId attributeId,
                                                                       uint8_t * buffer)
{
    ChipLogProgress(DeviceLayer, "HandleWriteEntityLocationAttribute: attrId=%d", attributeId);

    if ((attributeId == EntityLocation::Attributes::Id::Id) && (dev->IsReachable()))
    {
        chip::CharSpan idSpan(reinterpret_cast<const char *>(buffer + 1), buffer[0]); // First byte is length
        dev->SetEntityID(std::string(idSpan.data(), idSpan.size()));
    }
    else if ((attributeId == EntityLocation::Attributes::Location::Id) && (dev->IsReachable()))
    {
        chip::CharSpan locationSpan(reinterpret_cast<const char *>(buffer + 1), buffer[0]); // First byte is length
        dev->SetEntityLocation(std::string(locationSpan.data(), locationSpan.size()));
    }
    else
    {
        return Protocols::InteractionModel::Status::Failure;
    }

    return Protocols::InteractionModel::Status::Success;
}

Protocols::InteractionModel::Status HandleReadTempMeasurementAttribute(DeviceTempSensor * dev, chip::AttributeId attributeId,
                                                                       uint8_t * buffer, uint16_t maxReadLength)
{
    using namespace TemperatureMeasurement::Attributes;

    if ((attributeId == MeasuredValue::Id) && (maxReadLength == 2))
    {
        int16_t measuredValue = dev->GetMeasuredValue();
        memcpy(buffer, &measuredValue, sizeof(measuredValue));
    }
    else if ((attributeId == MinMeasuredValue::Id) && (maxReadLength == 2))
    {
        int16_t minValue = dev->mMin;
        memcpy(buffer, &minValue, sizeof(minValue));
    }
    else if ((attributeId == MaxMeasuredValue::Id) && (maxReadLength == 2))
    {
        int16_t maxValue = dev->mMax;
        memcpy(buffer, &maxValue, sizeof(maxValue));
    }
    else if ((attributeId == FeatureMap::Id) && (maxReadLength == 4))
    {
        uint32_t featureMap = ZCL_TEMPERATURE_SENSOR_FEATURE_MAP;
        memcpy(buffer, &featureMap, sizeof(featureMap));
    }
    else if ((attributeId == ClusterRevision::Id) && (maxReadLength == 2))
    {
        uint16_t clusterRevision = ZCL_TEMPERATURE_SENSOR_CLUSTER_REVISION;
        memcpy(buffer, &clusterRevision, sizeof(clusterRevision));
    }
    else
    {
        return Protocols::InteractionModel::Status::Failure;
    }

    return Protocols::InteractionModel::Status::Success;
}

Protocols::InteractionModel::Status emberAfExternalAttributeReadCallback(EndpointId endpoint, ClusterId clusterId,
                                                                         const EmberAfAttributeMetadata * attributeMetadata,
                                                                         uint8_t * buffer, uint16_t maxReadLength)
{
    uint16_t endpointIndex = emberAfGetDynamicIndexFromEndpoint(endpoint);

    Protocols::InteractionModel::Status ret = Protocols::InteractionModel::Status::Failure;

    if ((endpointIndex < CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT) && (gDevices[endpointIndex] != nullptr))
    {
        Device * dev = gDevices[endpointIndex];

        if (clusterId == BridgedDeviceBasicInformation::Id)
        {
            ret = HandleReadBridgedDeviceBasicAttribute(dev, attributeMetadata->attributeId, buffer, maxReadLength);
        }
        else if (clusterId == EntityLocation::Id)
        {
            ret = HandleReadEntityLocationAttribute(static_cast<DeviceEntityLocation *>(dev), attributeMetadata->attributeId,
                                                    buffer, maxReadLength);
        }
        else if (clusterId == TemperatureMeasurement::Id)
        {
            ret = HandleReadTempMeasurementAttribute(static_cast<DeviceTempSensor *>(dev), attributeMetadata->attributeId, buffer,
                                                     maxReadLength);
        }
    }

    return ret;
}

class BridgedPowerSourceAttrAccess : public AttributeAccessInterface
{
public:
    // Register on all endpoints.
    BridgedPowerSourceAttrAccess() : AttributeAccessInterface(Optional<EndpointId>::Missing(), PowerSource::Id) {}

    CHIP_ERROR
    Read(const ConcreteReadAttributePath & aPath, AttributeValueEncoder & aEncoder) override
    {
        uint16_t powerSourceDeviceIndex = CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT;

        if ((gDevices[powerSourceDeviceIndex] != nullptr))
        {
            DevicePowerSource * dev = static_cast<DevicePowerSource *>(gDevices[powerSourceDeviceIndex]);
            if (aPath.mEndpointId != dev->GetEndpointId())
            {
                return CHIP_IM_GLOBAL_STATUS(UnsupportedEndpoint);
            }
            switch (aPath.mAttributeId)
            {
            case PowerSource::Attributes::BatChargeLevel::Id:
                aEncoder.Encode(dev->GetBatChargeLevel());
                break;
            case PowerSource::Attributes::Order::Id:
                aEncoder.Encode(dev->GetOrder());
                break;
            case PowerSource::Attributes::Status::Id:
                aEncoder.Encode(dev->GetStatus());
                break;
            case PowerSource::Attributes::Description::Id:
                aEncoder.Encode(chip::CharSpan(dev->GetDescription().c_str(), dev->GetDescription().size()));
                break;
            case PowerSource::Attributes::EndpointList::Id: {
                std::vector<chip::EndpointId> & list = dev->GetEndpointList();
                DataModel::List<EndpointId> dm_list(chip::Span<chip::EndpointId>(list.data(), list.size()));
                aEncoder.Encode(dm_list);
                break;
            }
            case PowerSource::Attributes::ClusterRevision::Id:
                aEncoder.Encode(ZCL_POWER_SOURCE_CLUSTER_REVISION);
                break;
            case PowerSource::Attributes::FeatureMap::Id:
                aEncoder.Encode(dev->GetFeatureMap());
                break;

            case PowerSource::Attributes::BatReplacementNeeded::Id:
                aEncoder.Encode(false);
                break;
            case PowerSource::Attributes::BatReplaceability::Id:
                aEncoder.Encode(PowerSource::BatReplaceabilityEnum::kNotReplaceable);
                break;
            default:
                return CHIP_IM_GLOBAL_STATUS(UnsupportedAttribute);
            }
        }
        return CHIP_NO_ERROR;
    }
};

BridgedPowerSourceAttrAccess gPowerAttrAccess;

Protocols::InteractionModel::Status emberAfExternalAttributeWriteCallback(EndpointId endpoint, ClusterId clusterId,
                                                                          const EmberAfAttributeMetadata * attributeMetadata,
                                                                          uint8_t * buffer)
{
    uint16_t endpointIndex = emberAfGetDynamicIndexFromEndpoint(endpoint);

    Protocols::InteractionModel::Status ret = Protocols::InteractionModel::Status::Failure;

    // ChipLogProgress(DeviceLayer, "emberAfExternalAttributeWriteCallback: ep=%d", endpoint);

    if (endpointIndex < CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT)
    {
        Device * dev = gDevices[endpointIndex];

        if ((dev->IsReachable()) && (clusterId == EntityLocation::Id))
        {
            ret = HandleWriteEntityLocationAttribute(static_cast<DeviceEntityLocation *>(dev), attributeMetadata->attributeId,
                                                     buffer);
        }
    }

    return ret;
}

const EmberAfDeviceType gBridgedOnOffDeviceTypes[] = { { DEVICE_TYPE_LO_ON_OFF_LIGHT, DEVICE_VERSION_DEFAULT },
                                                       { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gBridgedEntityLocationDeviceTypes[] = { { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gBridgedComposedDeviceTypes[] = { { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT },
                                                          { DEVICE_TYPE_POWER_SOURCE, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gComposedTempSensorDeviceTypes[] = { { DEVICE_TYPE_TEMP_SENSOR, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gBridgedTempSensorDeviceTypes[] = { { DEVICE_TYPE_TEMP_SENSOR, DEVICE_VERSION_DEFAULT },
                                                            { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };

#define POLL_INTERVAL_MS (100)

bool kbhit()
{
    int byteswaiting;
    ioctl(0, FIONREAD, &byteswaiting);
    return byteswaiting > 0;
}

const int16_t oneDegree = 100;

// 位置推定システム用の関数
void UpdatePersonLocation(DeviceEntityLocation * person, const std::string & newLocation)
{
    if (person->IsReachable())
    {
        person->SetEntityLocation(newLocation);
        ChipLogProgress(DeviceLayer, "Person %s location updated to: %s", person->GetName(), newLocation.c_str());
    }
}

// 位置推定システムのステータス表示
void DisplayLocationSystem()
{
    ChipLogProgress(DeviceLayer, "=== Location Tracking System Status ===");

    DeviceEntityLocation * persons[] = { &Person1, &Person2, &Person3, &Person4 };

    for (int i = 0; i < 4; i++)
    {
        DeviceEntityLocation * person = persons[i];
        ChipLogProgress(DeviceLayer, "%s (ID: %s) - Location: %s [%s]", person->GetName(), person->GetEntityID().c_str(),
                        person->GetEntityLocation().c_str(), person->IsReachable() ? "Online" : "Offline");
    }
    ChipLogProgress(DeviceLayer, "=====================================");
}

// 位置推定のシミュレーション用関数
void SimulateLocationTracking()
{
    static int simulation_step = 0;
    simulation_step++;

    // 各人の位置をランダムに更新（実際のシステムでは位置推定アルゴリズムからの結果）
    switch (simulation_step % 8)
    {
    case 0:
        UpdatePersonLocation(&Person1, "Living Room");
        UpdatePersonLocation(&Person2, "Kitchen");
        break;
    case 1:
        UpdatePersonLocation(&Person1, "Kitchen");
        UpdatePersonLocation(&Person3, "Office");
        break;
    case 2:
        UpdatePersonLocation(&Person2, "Bedroom");
        UpdatePersonLocation(&Person4, "Living Room");
        break;
    case 3:
        UpdatePersonLocation(&Person1, "Office");
        UpdatePersonLocation(&Person2, "Living Room");
        break;
    case 4:
        UpdatePersonLocation(&Person3, "Kitchen");
        UpdatePersonLocation(&Person4, "Bedroom");
        break;
    case 5:
        UpdatePersonLocation(&Person1, "Bedroom");
        UpdatePersonLocation(&Person3, "Bathroom");
        break;
    case 6:
        UpdatePersonLocation(&Person2, "Office");
        UpdatePersonLocation(&Person4, "Kitchen");
        break;
    case 7:
        UpdatePersonLocation(&Person1, "Garden");
        UpdatePersonLocation(&Person2, "Entrance");
        break;
    }

    DisplayLocationSystem();
}

void * bridge_polling_thread(void * context)
{
    while (true)
    {
        if (kbhit())
        {
            int ch = getchar();
            // 位置推定システム用コマンド
            if (ch == 'p')
            {
                // 位置推定システムのステータス表示
                DisplayLocationSystem();
            }
            if (ch == 's')
            {
                // 位置推定のシミュレーション実行
                SimulateLocationTracking();
            }
            if (ch == '1')
            {
                // Person1 を Living Room に移動
                UpdatePersonLocation(&Person1, "Living Room");
            }
            if (ch == '2')
            {
                // Person2 を Kitchen に移動
                UpdatePersonLocation(&Person2, "Kitchen");
            }
            if (ch == '3')
            {
                // Person3 を Office に移動
                UpdatePersonLocation(&Person3, "Office");
            }
            if (ch == '4')
            {
                // Person4 を Bedroom に移動
                UpdatePersonLocation(&Person4, "Bedroom");
            }
            if (ch == 'a')
            {
                // 全員を Living Room に集合
                UpdatePersonLocation(&Person1, "Living Room");
                UpdatePersonLocation(&Person2, "Living Room");
                UpdatePersonLocation(&Person3, "Living Room");
                UpdatePersonLocation(&Person4, "Living Room");
                ChipLogProgress(DeviceLayer, "All persons moved to Living Room");
            }
            if (ch == 'd')
            {
                // 全員を異なる部屋に分散
                UpdatePersonLocation(&Person1, "Living Room");
                UpdatePersonLocation(&Person2, "Kitchen");
                UpdatePersonLocation(&Person3, "Office");
                UpdatePersonLocation(&Person4, "Bedroom");
                ChipLogProgress(DeviceLayer, "Persons distributed to different rooms");
            }
            continue;
        }

        // Sleep to avoid tight loop reading commands
        usleep(POLL_INTERVAL_MS * 1000);
    }

    return nullptr;
}

void ApplicationInit()
{
    // Clear out the device database
    memset(gDevices, 0, sizeof(gDevices));

    // Setup Location Tracking System
    ChipLogProgress(DeviceLayer, "Initializing Location Tracking System...");

    // 各人物エンティティの初期化
    Person1.SetReachable(true);
    Person2.SetReachable(true);
    Person3.SetReachable(true);
    Person4.SetReachable(true);

    // 初期位置を設定
    Person1.SetEntityID("person_001");
    Person1.SetEntityLocation("Entrance");

    Person2.SetEntityID("person_002");
    Person2.SetEntityLocation("Living Room");

    Person3.SetEntityID("person_003");
    Person3.SetEntityLocation("Office");

    Person4.SetEntityID("person_004");
    Person4.SetEntityLocation("Kitchen");

    // コールバック設定
    Person1.SetChangeCallback(&HandleDeviceEntityLocationStatusChanged);
    Person2.SetChangeCallback(&HandleDeviceEntityLocationStatusChanged);
    Person3.SetChangeCallback(&HandleDeviceEntityLocationStatusChanged);
    Person4.SetChangeCallback(&HandleDeviceEntityLocationStatusChanged);

    // Set starting endpoint id where dynamic endpoints will be assigned, which
    // will be the next consecutive endpoint id after the last fixed endpoint.
    gFirstDynamicEndpointId = static_cast<chip::EndpointId>(
        static_cast<int>(emberAfEndpointFromIndex(static_cast<uint16_t>(emberAfFixedEndpointCount() - 1))) + 1);
    gCurrentEndpointId = gFirstDynamicEndpointId;

    // Disable last fixed endpoint, which is used as a placeholder for all of the
    // supported clusters so that ZAP will generated the requisite code.
    emberAfEndpointEnableDisable(emberAfEndpointFromIndex(static_cast<uint16_t>(emberAfFixedEndpointCount() - 1)), false);

    // Add Person entities to Matter endpoints
    AddDeviceEndpoint(&Person1, &bridgedEntityLoEndpoint, Span<const EmberAfDeviceType>(gBridgedEntityLocationDeviceTypes),
                      Span<DataVersion>(gPerson1DataVersions), 1);
    AddDeviceEndpoint(&Person2, &bridgedEntityLoEndpoint, Span<const EmberAfDeviceType>(gBridgedEntityLocationDeviceTypes),
                      Span<DataVersion>(gPerson2DataVersions), 1);
    AddDeviceEndpoint(&Person3, &bridgedEntityLoEndpoint, Span<const EmberAfDeviceType>(gBridgedEntityLocationDeviceTypes),
                      Span<DataVersion>(gPerson3DataVersions), 1);
    AddDeviceEndpoint(&Person4, &bridgedEntityLoEndpoint, Span<const EmberAfDeviceType>(gBridgedEntityLocationDeviceTypes),
                      Span<DataVersion>(gPerson4DataVersions), 1);

    // 初期ステータス表示
    DisplayLocationSystem();

    ChipLogProgress(DeviceLayer, "Location Tracking System initialized successfully!");
    ChipLogProgress(DeviceLayer, "Commands: p=status, s=simulate, 1-4=move person, a=gather all, d=distribute");

    {
        pthread_t poll_thread;
        int res = pthread_create(&poll_thread, nullptr, bridge_polling_thread, nullptr);
        if (res)
        {
            printf("Error creating polling thread: %d\n", res);
            exit(1);
        }
    }
}

void ApplicationShutdown() {}

int main(int argc, char * argv[])
{
    if (ChipLinuxAppInit(argc, argv) != 0)
    {
        return -1;
    }
    ChipLinuxAppMainLoop();
    return 0;
}
