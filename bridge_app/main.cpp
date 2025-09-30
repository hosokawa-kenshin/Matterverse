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
 *    See the License for the specific language governing permissions and
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
#include "MQTTClient.h"
#include "main.h"
#include <app/server/Server.h>

#include <cassert>
#include <iostream>
#include <memory>
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

const int kNodeLabelSize = 32;
const int kUniqueIdSize  = 32;
// Current ZCL implementation of Struct uses a max-size array of 254 bytes
const int kDescriptorAttributeArraySize = 254;

EndpointId gCurrentEndpointId;
EndpointId gFirstDynamicEndpointId;
// Power source is on the same endpoint as the composed device
Device * gDevices[CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT + 1];
std::vector<Room *> gRooms;
std::vector<Action *> gActions;

const int16_t minMeasuredValue     = -27315;
const int16_t maxMeasuredValue     = 32766;
const int16_t initialMeasuredValue = 100;

// MQTT Client instance
std::unique_ptr<mqtt::MQTTClient> gMQTTClient;

// ENDPOINT DEFINITIONS:
// =================================================================================
//
// Endpoint definitions will be reused across multiple endpoints for every instance of the
// endpoint type.
// There will be no intrinsic storage for the endpoint attributes declared here.
// Instead, all attributes will be treated as EXTERNAL, and therefore all reads
// or writes to the attributes must be handled within the emberAfExternalAttributeWriteCallback
// and emberAfExternalAttributeReadCallback functions declared herein. This fits
// the typical model of a bridge, since a bridge typically maintains its own
// state database representing the devices connected to it.

// Device types for dynamic endpoints: TODO Need a generated file from ZAP to define these!
// (taken from matter-devices.xml)
#define DEVICE_TYPE_BRIDGED_NODE 0x0013
// (taken from lo-devices.xml)
#define DEVICE_TYPE_LO_ON_OFF_LIGHT 0x0100
// (taken from matter-devices.xml)
#define DEVICE_TYPE_POWER_SOURCE 0x0011
// (taken from matter-devices.xml)
#define DEVICE_TYPE_TEMP_SENSOR 0x0302

// Device Version for dynamic endpoints:
#define DEVICE_VERSION_DEFAULT 1

// ---------------------------------------------------------------------------
//
// LIGHT ENDPOINT: contains the following clusters:
//   - On/Off
//   - Descriptor
//   - Bridged Device Basic Information

// Declare On/Off cluster attributes
DECLARE_DYNAMIC_ATTRIBUTE_LIST_BEGIN(onOffAttrs)
DECLARE_DYNAMIC_ATTRIBUTE(OnOff::Attributes::OnOff::Id, BOOLEAN, 1, 0), /* on/off */
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

// Declare Cluster List for Bridged Light endpoint
// TODO: It's not clear whether it would be better to get the command lists from
// the ZAP config on our last fixed endpoint instead.
constexpr CommandId onOffIncomingCommands[] = {
    app::Clusters::OnOff::Commands::Off::Id,
    app::Clusters::OnOff::Commands::On::Id,
    app::Clusters::OnOff::Commands::Toggle::Id,
    app::Clusters::OnOff::Commands::OffWithEffect::Id,
    app::Clusters::OnOff::Commands::OnWithRecallGlobalScene::Id,
    app::Clusters::OnOff::Commands::OnWithTimedOff::Id,
    kInvalidCommandId,
};

DECLARE_DYNAMIC_CLUSTER_LIST_BEGIN(bridgedLightClusters)
DECLARE_DYNAMIC_CLUSTER(OnOff::Id, onOffAttrs, ZAP_CLUSTER_MASK(SERVER), onOffIncomingCommands, nullptr),
    DECLARE_DYNAMIC_CLUSTER(Descriptor::Id, descriptorAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(BridgedDeviceBasicInformation::Id, bridgedDeviceBasicAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr,
                            nullptr) DECLARE_DYNAMIC_CLUSTER_LIST_END;

// Declare Bridged Light endpoint
DECLARE_DYNAMIC_ENDPOINT(bridgedLightEndpoint, bridgedLightClusters);
DataVersion gLight1DataVersions[ArraySize(bridgedLightClusters)];
DataVersion gLight2DataVersions[ArraySize(bridgedLightClusters)];

DeviceOnOff Light1("Light 1", "Office");
DeviceOnOff Light2("Light 2", "Office");

DeviceTempSensor TempSensor1("TempSensor 1", "Office", minMeasuredValue, maxMeasuredValue, initialMeasuredValue);
DeviceTempSensor TempSensor2("TempSensor 2", "Office", minMeasuredValue, maxMeasuredValue, initialMeasuredValue);

// Declare Bridged endpoints used for Action clusters
DataVersion gActionLight1DataVersions[ArraySize(bridgedLightClusters)];
DataVersion gActionLight2DataVersions[ArraySize(bridgedLightClusters)];
DataVersion gActionLight3DataVersions[ArraySize(bridgedLightClusters)];
DataVersion gActionLight4DataVersions[ArraySize(bridgedLightClusters)];

DeviceOnOff ActionLight1("Action Light 1", "Room 1");
DeviceOnOff ActionLight2("Action Light 2", "Room 1");
DeviceOnOff ActionLight3("Action Light 3", "Room 2");
DeviceOnOff ActionLight4("Action Light 4", "Room 2");

// Setup composed device with two temperature sensors and a power source
ComposedDevice gComposedDevice("Composed Device", "Bedroom");
DeviceTempSensor ComposedTempSensor1("Composed TempSensor 1", "Bedroom", minMeasuredValue, maxMeasuredValue, initialMeasuredValue);
DeviceTempSensor ComposedTempSensor2("Composed TempSensor 2", "Bedroom", minMeasuredValue, maxMeasuredValue, initialMeasuredValue);
DevicePowerSource ComposedPowerSource("Composed Power Source", "Bedroom", PowerSource::Feature::kBattery);

Room room1("Room 1", 0xE001, Actions::EndpointListTypeEnum::kRoom, true);
Room room2("Room 2", 0xE002, Actions::EndpointListTypeEnum::kRoom, true);
Room room3("Zone 3", 0xE003, Actions::EndpointListTypeEnum::kZone, false);

Action action1(0x1001, "Room 1 On", Actions::ActionTypeEnum::kAutomation, 0xE001, 0x1, Actions::ActionStateEnum::kInactive, true);
Action action2(0x1002, "Turn On Room 2", Actions::ActionTypeEnum::kAutomation, 0xE002, 0x01, Actions::ActionStateEnum::kInactive,
               true);
Action action3(0x1003, "Turn Off Room 1", Actions::ActionTypeEnum::kAutomation, 0xE003, 0x01, Actions::ActionStateEnum::kInactive,
               false);

DECLARE_DYNAMIC_ATTRIBUTE_LIST_BEGIN(tempSensorAttrs)
DECLARE_DYNAMIC_ATTRIBUTE(TemperatureMeasurement::Attributes::MeasuredValue::Id, INT16S, 2, 0),        /* Measured Value */
    DECLARE_DYNAMIC_ATTRIBUTE(TemperatureMeasurement::Attributes::MinMeasuredValue::Id, INT16S, 2, 0), /* Min Measured Value */
    DECLARE_DYNAMIC_ATTRIBUTE(TemperatureMeasurement::Attributes::MaxMeasuredValue::Id, INT16S, 2, 0), /* Max Measured Value */
    DECLARE_DYNAMIC_ATTRIBUTE(TemperatureMeasurement::Attributes::FeatureMap::Id, BITMAP32, 4, 0),     /* FeatureMap */
    DECLARE_DYNAMIC_ATTRIBUTE_LIST_END();

// ---------------------------------------------------------------------------
//
// TEMPERATURE SENSOR ENDPOINT: contains the following clusters:
//   - Temperature measurement
//   - Descriptor
//   - Bridged Device Basic Information
DECLARE_DYNAMIC_CLUSTER_LIST_BEGIN(bridgedTempSensorClusters)
DECLARE_DYNAMIC_CLUSTER(TemperatureMeasurement::Id, tempSensorAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(Descriptor::Id, descriptorAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(BridgedDeviceBasicInformation::Id, bridgedDeviceBasicAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER_LIST_END;

// Declare Bridged Light endpoint
DECLARE_DYNAMIC_ENDPOINT(bridgedTempSensorEndpoint, bridgedTempSensorClusters);
DataVersion gTempSensor1DataVersions[ArraySize(bridgedTempSensorClusters)];
DataVersion gTempSensor2DataVersions[ArraySize(bridgedTempSensorClusters)];

// ---------------------------------------------------------------------------
//
// COMPOSED DEVICE ENDPOINT: contains the following clusters:
//   - Descriptor
//   - Bridged Device Basic Information
//   - Power source

// Composed Device Configuration
DECLARE_DYNAMIC_ATTRIBUTE_LIST_BEGIN(powerSourceAttrs)
DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::BatChargeLevel::Id, ENUM8, 1, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::BatReplacementNeeded::Id, BOOLEAN, 1, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::BatReplaceability::Id, ENUM8, 1, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::Order::Id, INT8U, 1, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::Status::Id, ENUM8, 1, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::Description::Id, CHAR_STRING, 32, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::EndpointList::Id, ARRAY, 0, 0),
    DECLARE_DYNAMIC_ATTRIBUTE(PowerSource::Attributes::FeatureMap::Id, BITMAP32, 4, 0), DECLARE_DYNAMIC_ATTRIBUTE_LIST_END();

DECLARE_DYNAMIC_CLUSTER_LIST_BEGIN(bridgedComposedDeviceClusters)
DECLARE_DYNAMIC_CLUSTER(Descriptor::Id, descriptorAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(BridgedDeviceBasicInformation::Id, bridgedDeviceBasicAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER(PowerSource::Id, powerSourceAttrs, ZAP_CLUSTER_MASK(SERVER), nullptr, nullptr),
    DECLARE_DYNAMIC_CLUSTER_LIST_END;

DECLARE_DYNAMIC_ENDPOINT(bridgedComposedDeviceEndpoint, bridgedComposedDeviceClusters);
DataVersion gComposedDeviceDataVersions[ArraySize(bridgedComposedDeviceClusters)];
DataVersion gComposedTempSensor1DataVersions[ArraySize(bridgedTempSensorClusters)];
DataVersion gComposedTempSensor2DataVersions[ArraySize(bridgedTempSensorClusters)];

} // namespace

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

int RemoveDeviceEndpoint(Device * dev)
{
    uint8_t index = 0;
    while (index < CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT)
    {
        if (gDevices[index] == dev)
        {
            // Todo: Update this to schedule the work rather than use this lock
            DeviceLayer::StackLock lock;
            // Silence complaints about unused ep when progress logging
            // disabled.
            [[maybe_unused]] EndpointId ep = emberAfClearDynamicEndpoint(index);
            gDevices[index]                = nullptr;
            ChipLogProgress(DeviceLayer, "Removed device %s from dynamic endpoint %d (index=%d)", dev->GetName(), ep, index);
            return index;
        }
        index++;
    }
    return -1;
}

std::vector<EndpointListInfo> GetEndpointListInfo(chip::EndpointId parentId)
{
    std::vector<EndpointListInfo> infoList;

    for (auto room : gRooms)
    {
        if (room->getIsVisible())
        {
            EndpointListInfo info(room->getEndpointListId(), room->getName(), room->getType());
            int index = 0;
            while (index < CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT)
            {
                if ((gDevices[index] != nullptr) && (gDevices[index]->GetParentEndpointId() == parentId))
                {
                    std::string location;
                    if (room->getType() == Actions::EndpointListTypeEnum::kZone)
                    {
                        location = gDevices[index]->GetZone();
                    }
                    else
                    {
                        location = gDevices[index]->GetLocation();
                    }
                    if (room->getName().compare(location) == 0)
                    {
                        info.AddEndpointId(gDevices[index]->GetEndpointId());
                    }
                }
                index++;
            }
            if (info.GetEndpointListSize() > 0)
            {
                infoList.push_back(info);
            }
        }
    }

    return infoList;
}

std::vector<Action *> GetActionListInfo(chip::EndpointId parentId)
{
    return gActions;
}

namespace {
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
} // anonymous namespace

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

void HandleDeviceOnOffStatusChanged(DeviceOnOff * dev, DeviceOnOff::Changed_t itemChangedMask)
{
    if (itemChangedMask & (DeviceOnOff::kChanged_Reachable | DeviceOnOff::kChanged_Name | DeviceOnOff::kChanged_Location))
    {
        HandleDeviceStatusChanged(static_cast<Device *>(dev), (Device::Changed_t) itemChangedMask);
    }

    if (itemChangedMask & DeviceOnOff::kChanged_OnOff)
    {
        ScheduleReportingCallback(dev, OnOff::Id, OnOff::Attributes::OnOff::Id);
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

Protocols::InteractionModel::Status HandleReadOnOffAttribute(DeviceOnOff * dev, chip::AttributeId attributeId, uint8_t * buffer,
                                                             uint16_t maxReadLength)
{
    ChipLogProgress(DeviceLayer, "HandleReadOnOffAttribute: attrId=%d, maxReadLength=%d", attributeId, maxReadLength);

    if ((attributeId == OnOff::Attributes::OnOff::Id) && (maxReadLength == 1))
    {
        *buffer = dev->IsOn() ? 1 : 0;
    }
    else if ((attributeId == OnOff::Attributes::ClusterRevision::Id) && (maxReadLength == 2))
    {
        uint16_t rev = ZCL_ON_OFF_CLUSTER_REVISION;
        memcpy(buffer, &rev, sizeof(rev));
    }
    else
    {
        return Protocols::InteractionModel::Status::Failure;
    }

    return Protocols::InteractionModel::Status::Success;
}

Protocols::InteractionModel::Status HandleWriteOnOffAttribute(DeviceOnOff * dev, chip::AttributeId attributeId, uint8_t * buffer)
{
    ChipLogProgress(DeviceLayer, "HandleWriteOnOffAttribute: attrId=%d", attributeId);

    if ((attributeId == OnOff::Attributes::OnOff::Id) && (dev->IsReachable()))
    {
        if (*buffer)
        {
            dev->SetOnOff(true);
        }
        else
        {
            dev->SetOnOff(false);
        }
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
        else if (clusterId == OnOff::Id)
        {
            ret = HandleReadOnOffAttribute(static_cast<DeviceOnOff *>(dev), attributeMetadata->attributeId, buffer, maxReadLength);
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

// MQTT message handler
void OnMQTTMessage(const std::string & topic, const std::string & payload)
{
    ChipLogProgress(DeviceLayer, "MQTT Message - Topic: %s, Payload: %s", topic.c_str(), payload.c_str());

    // Message processing is now handled automatically by MQTTClient::ProcessHomieMessage()
    // The data is stored in SQLite database within the MQTT client

    // Optionally log database statistics periodically
    static int message_count = 0;
    message_count++;

    if (message_count % 50 == 0 && gMQTTClient)
    {
        // Every 50 messages, log the number of devices in database
        auto devices = gMQTTClient->GetAllDevices();
        ChipLogProgress(DeviceLayer, "Database contains %zu Matter devices after %d messages", devices.size(), message_count);

        // Log some device details
        for (const auto & device : devices)
        {
            ChipLogProgress(DeviceLayer, "Device: %s (Name: %s, State: %s)", device.topic_id.c_str(), device.device_name.c_str(),
                            device.state.c_str());
        }
    }
}

// MQTT connection handler
void OnMQTTConnection(bool connected)
{
    if (connected)
    {
        ChipLogProgress(DeviceLayer, "MQTT Client connected successfully");

        // Subscribe to Homie protocol topics
        if (gMQTTClient)
        {
            gMQTTClient->Subscribe("homie/#", 0);
            ChipLogProgress(DeviceLayer, "Subscribed to homie/# topics");
        }
    }
    else
    {
        ChipLogProgress(DeviceLayer, "MQTT Client disconnected");
    }
}

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

        if ((dev->IsReachable()) && (clusterId == OnOff::Id))
        {
            ret = HandleWriteOnOffAttribute(static_cast<DeviceOnOff *>(dev), attributeMetadata->attributeId, buffer);
        }
    }

    return ret;
}

void runOnOffRoomAction(Room * room, bool actionOn, EndpointId endpointId, uint16_t actionID, uint32_t invokeID, bool hasInvokeID)
{
    if (hasInvokeID)
    {
        Actions::Events::StateChanged::Type event{ actionID, invokeID, Actions::ActionStateEnum::kActive };
        EventNumber eventNumber;
        chip::app::LogEvent(event, endpointId, eventNumber);
    }

    // Check and run the action for ActionLight1 - ActionLight4
    if (room->getName().compare(ActionLight1.GetLocation()) == 0)
    {
        ActionLight1.SetOnOff(actionOn);
    }
    if (room->getName().compare(ActionLight2.GetLocation()) == 0)
    {
        ActionLight2.SetOnOff(actionOn);
    }
    if (room->getName().compare(ActionLight3.GetLocation()) == 0)
    {
        ActionLight3.SetOnOff(actionOn);
    }
    if (room->getName().compare(ActionLight4.GetLocation()) == 0)
    {
        ActionLight4.SetOnOff(actionOn);
    }

    if (hasInvokeID)
    {
        Actions::Events::StateChanged::Type event{ actionID, invokeID, Actions::ActionStateEnum::kInactive };
        EventNumber eventNumber;
        chip::app::LogEvent(event, endpointId, eventNumber);
    }
}

bool emberAfActionsClusterInstantActionCallback(app::CommandHandler * commandObj, const app::ConcreteCommandPath & commandPath,
                                                const Actions::Commands::InstantAction::DecodableType & commandData)
{
    bool hasInvokeID      = false;
    uint32_t invokeID     = 0;
    EndpointId endpointID = commandPath.mEndpointId;
    auto & actionID       = commandData.actionID;

    if (commandData.invokeID.HasValue())
    {
        hasInvokeID = true;
        invokeID    = commandData.invokeID.Value();
    }

    if (actionID == action1.getActionId() && action1.getIsVisible())
    {
        // Turn On Lights in Room 1
        runOnOffRoomAction(&room1, true, endpointID, actionID, invokeID, hasInvokeID);
        commandObj->AddStatus(commandPath, Protocols::InteractionModel::Status::Success);
        return true;
    }
    if (actionID == action2.getActionId() && action2.getIsVisible())
    {
        // Turn On Lights in Room 2
        runOnOffRoomAction(&room2, true, endpointID, actionID, invokeID, hasInvokeID);
        commandObj->AddStatus(commandPath, Protocols::InteractionModel::Status::Success);
        return true;
    }
    if (actionID == action3.getActionId() && action3.getIsVisible())
    {
        // Turn Off Lights in Room 1
        runOnOffRoomAction(&room1, false, endpointID, actionID, invokeID, hasInvokeID);
        commandObj->AddStatus(commandPath, Protocols::InteractionModel::Status::Success);
        return true;
    }

    commandObj->AddStatus(commandPath, Protocols::InteractionModel::Status::NotFound);
    return true;
}

const EmberAfDeviceType gBridgedOnOffDeviceTypes[] = { { DEVICE_TYPE_LO_ON_OFF_LIGHT, DEVICE_VERSION_DEFAULT },
                                                       { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gBridgedComposedDeviceTypes[] = { { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT },
                                                          { DEVICE_TYPE_POWER_SOURCE, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gComposedTempSensorDeviceTypes[] = { { DEVICE_TYPE_TEMP_SENSOR, DEVICE_VERSION_DEFAULT } };

const EmberAfDeviceType gBridgedTempSensorDeviceTypes[] = { { DEVICE_TYPE_TEMP_SENSOR, DEVICE_VERSION_DEFAULT },
                                                            { DEVICE_TYPE_BRIDGED_NODE, DEVICE_VERSION_DEFAULT } };

#define POLL_INTERVAL_MS (100)
uint8_t poll_prescale = 0;

const int16_t oneDegree = 100;

// Device type information for registration
struct DeviceTypeInfo
{
    const char * name;
    const char * description;
};

// Available device types for MQTT device registration
static const DeviceTypeInfo gAvailableDeviceTypes[] = {
    { "OnOff Light", "Basic on/off light control" },
    { "Dimmable Light", "Dimmable light with level control" },
    { "Temperature Sensor", "Temperature measurement device" },
};

static const size_t gDeviceTypeCount = sizeof(gAvailableDeviceTypes) / sizeof(gAvailableDeviceTypes[0]);

// Command enumeration for CLI
enum class CLICommand
{
    HELP,
    REGISTER,
    QUIT,
    EMPTY,
    OTHER
};

// Convert string to CLI command enum
CLICommand getCommandType(const std::string & command)
{
    if (command == "help" || command == "h")
        return CLICommand::HELP;
    else if (command == "register")
        return CLICommand::REGISTER;
    else if (command == "quit" || command == "q" || command == "exit")
        return CLICommand::QUIT;
    else if (command.empty())
        return CLICommand::EMPTY;
    else
        return CLICommand::OTHER;
}

void * bridge_polling_thread(void * context)
{
    bool light1_added = true;
    bool light2_added = false;
    std::string line;

    // Print initial CLI prompt with welcome message
    std::cout << "Matter Bridge CLI - Type 'help' for available commands" << std::endl;
    std::cout << "> " << std::flush;

    while (true)
    {
        if (std::getline(std::cin, line))
        {
            // Handle full commands using switch statement
            CLICommand cmd = getCommandType(line);
            switch (cmd)
            {
            case CLICommand::HELP:
                std::cout << "Available commands:" << std::endl;
                std::cout << "  2 - Add Light2" << std::endl;
                std::cout << "  4 - Remove Light1" << std::endl;
                std::cout << "  5 - Add Light1 back" << std::endl;
                std::cout << "  b - Rename lights to 'Light 1b' and 'Light 2b'" << std::endl;
                std::cout << "  c - Toggle lights state" << std::endl;
                std::cout << "  t - Increase temperature sensor readings" << std::endl;
                std::cout << "  r - Rename Room 1" << std::endl;
                std::cout << "  f - Move Action Light 3 to Room 1" << std::endl;
                std::cout << "  i - Hide Room 2" << std::endl;
                std::cout << "  l - Show Zone 3 and move Action Light 2" << std::endl;
                std::cout << "  m - Rename action to 'Turn On Room 1'" << std::endl;
                std::cout << "  n - Hide 'Turn on Room 2 lights' action" << std::endl;
                std::cout << "  o - Show 'Turn off Room 1 renamed lights' action" << std::endl;
                std::cout << "  u - Set TempSensor1 unreachable" << std::endl;
                std::cout << "  v - Set TempSensor1 reachable" << std::endl;
                std::cout << "  help, h - Show this help message" << std::endl;
                std::cout << "  register - Interactive MQTT device registration" << std::endl;
                std::cout << "  quit, q, exit - Exit the application" << std::endl;
                break;

            case CLICommand::REGISTER: {
                std::cout << "=== MQTT Device Registration ===" << std::endl;
                if (!gMQTTClient)
                {
                    std::cout << "Error: MQTT client not initialized." << std::endl;
                    break;
                }

                auto devices = gMQTTClient->GetAllDevices();
                if (devices.empty())
                {
                    std::cout << "No MQTT devices found in database." << std::endl;
                    break;
                }

                std::cout << "Available MQTT devices:" << std::endl;
                int index = 1;
                for (const auto & device : devices)
                {
                    std::cout << "  " << index << ". Device ID: " << device.topic_id << std::endl;
                    if (!device.device_name.empty())
                    {
                        std::cout << "     Name: " << device.device_name << std::endl;
                    }
                    if (!device.state.empty())
                    {
                        std::cout << "     State: " << device.state << std::endl;
                    }
                    if (!device.nodes.empty())
                    {
                        std::cout << "     Nodes: " << device.nodes << std::endl;
                    }
                    std::cout << std::endl;
                    index++;
                }

                std::cout << "Select a device (1-" << devices.size() << ", or 0 to cancel): " << std::flush;
                std::string deviceSelection;
                if (!std::getline(std::cin, deviceSelection))
                {
                    std::cout << "Input error. Registration cancelled." << std::endl;
                    break;
                }

                int deviceIndex = std::atoi(deviceSelection.c_str());
                if (deviceIndex == 0)
                {
                    std::cout << "Registration cancelled." << std::endl;
                    break;
                }
                if (deviceIndex < 1 || deviceIndex > static_cast<int>(devices.size()))
                {
                    std::cout << "Invalid device selection. Registration cancelled." << std::endl;
                    break;
                }

                const auto & selectedDevice = devices[deviceIndex - 1];
                std::cout << "Selected device: " << selectedDevice.topic_id << std::endl;

                std::cout << "\nAvailable Device Types:" << std::endl;
                for (size_t i = 0; i < gDeviceTypeCount; i++)
                {
                    std::cout << "  " << (i + 1) << ". " << gAvailableDeviceTypes[i].name << " - "
                              << gAvailableDeviceTypes[i].description << std::endl;
                }

                std::cout << "Select a device type (1-" << gDeviceTypeCount << ", or 0 to cancel): " << std::flush;
                std::string typeSelection;
                if (!std::getline(std::cin, typeSelection))
                {
                    std::cout << "Input error. Registration cancelled." << std::endl;
                    break;
                }

                int typeIndex = std::atoi(typeSelection.c_str());
                if (typeIndex == 0)
                {
                    std::cout << "Registration cancelled." << std::endl;
                    break;
                }
                if (typeIndex < 1 || typeIndex > static_cast<int>(gDeviceTypeCount))
                {
                    std::cout << "Invalid device type selection. Registration cancelled." << std::endl;
                    break;
                }

                const auto & selectedType = gAvailableDeviceTypes[typeIndex - 1];
                std::cout << "Selected device type: " << selectedType.name << std::endl;

                std::cout << "\n=== Registration Summary ===" << std::endl;
                std::cout << "MQTT Device: " << selectedDevice.topic_id << std::endl;
                std::cout << "Device Type: " << selectedType.name << std::endl;
                std::cout << "Registration processing will be implemented here..." << std::endl;
                break;
            }

            case CLICommand::QUIT:
                std::cout << "Exiting..." << std::endl;
                return nullptr;

            case CLICommand::EMPTY:
                // Just show prompt again for empty input
                break;

            case CLICommand::OTHER: {
                // Process each character in the line for backward compatibility with existing commands
                for (char ch : line)
                {
                    switch (ch)
                    {
                    case '2':
                        if (!light2_added)
                        {
                            // TC-BR-2 step 2, Add Light2
                            AddDeviceEndpoint(&Light2, &bridgedLightEndpoint,
                                              Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                                              Span<DataVersion>(gLight2DataVersions), 1);
                            light2_added = true;
                            std::cout << "Light2 added" << std::endl;
                        }
                        break;

                    case '4':
                        if (light1_added)
                        {
                            // TC-BR-2 step 4, Remove Light 1
                            RemoveDeviceEndpoint(&Light1);
                            light1_added = false;
                            std::cout << "Light1 removed" << std::endl;
                        }
                        break;

                    case '5':
                        if (!light1_added)
                        {
                            // TC-BR-2 step 5, Add Light 1 back
                            AddDeviceEndpoint(&Light1, &bridgedLightEndpoint,
                                              Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                                              Span<DataVersion>(gLight1DataVersions), 1);
                            light1_added = true;
                            std::cout << "Light1 added back" << std::endl;
                        }
                        break;

                    case 'b':
                        // TC-BR-3 step 1b, rename lights
                        if (light1_added)
                        {
                            Light1.SetName("Light 1b");
                        }
                        if (light2_added)
                        {
                            Light2.SetName("Light 2b");
                        }
                        std::cout << "Lights renamed to 'Light 1b' and 'Light 2b'" << std::endl;
                        break;

                    case 'c':
                        // TC-BR-3 step 2c, change the state of the lights
                        if (light1_added)
                        {
                            Light1.Toggle();
                        }
                        if (light2_added)
                        {
                            Light2.Toggle();
                        }
                        std::cout << "Lights toggled" << std::endl;
                        break;

                    case 't':
                        // TC-BR-4 step 1g, change the state of the temperature sensors
                        TempSensor1.SetMeasuredValue(static_cast<int16_t>(TempSensor1.GetMeasuredValue() + oneDegree));
                        TempSensor2.SetMeasuredValue(static_cast<int16_t>(TempSensor2.GetMeasuredValue() + oneDegree));
                        ComposedTempSensor1.SetMeasuredValue(
                            static_cast<int16_t>(ComposedTempSensor1.GetMeasuredValue() + oneDegree));
                        ComposedTempSensor2.SetMeasuredValue(
                            static_cast<int16_t>(ComposedTempSensor2.GetMeasuredValue() + oneDegree));
                        std::cout << "Temperature sensors increased by 1 degree" << std::endl;
                        break;

                    // Commands used for the actions cluster test plan.
                    case 'r':
                        // TC-ACT-2.2 step 2c, rename "Room 1"
                        room1.setName("Room 1 renamed");
                        ActionLight1.SetLocation(room1.getName());
                        ActionLight2.SetLocation(room1.getName());
                        break;

                    case 'f':
                        // TC-ACT-2.2 step 2f, move "Action Light 3" from "Room 2" to "Room 1"
                        ActionLight3.SetLocation(room1.getName());
                        break;

                    case 'i':
                        // TC-ACT-2.2 step 2i, remove "Room 2" (make it not visible in the endpoint list), do not remove the lights
                        room2.setIsVisible(false);
                        break;

                    case 'l':
                        // TC-ACT-2.2 step 2l, add a new "Zone 3" and add "Action Light 2" to the new zone
                        room3.setIsVisible(true);
                        ActionLight2.SetZone("Zone 3");
                        break;

                    case 'm':
                        // TC-ACT-2.2 step 3c, rename "Turn on Room 1 lights"
                        action1.setName("Turn On Room 1");
                        break;

                    case 'n':
                        // TC-ACT-2.2 step 3f, remove "Turn on Room 2 lights"
                        action2.setIsVisible(false);
                        break;

                    case 'o':
                        // TC-ACT-2.2 step 3i, add "Turn off Room 1 renamed lights"
                        action3.setIsVisible(true);
                        break;

                    // Commands used for the Bridged Device Basic Information test plan
                    case 'u':
                        // TC-BRBINFO-2.2 step 2 "Set reachable to false"
                        TempSensor1.SetReachable(false);
                        std::cout << "TempSensor1 set to unreachable" << std::endl;
                        break;

                    case 'v':
                        // TC-BRBINFO-2.2 step 2 "Set reachable to true"
                        TempSensor1.SetReachable(true);
                        std::cout << "TempSensor1 set to reachable" << std::endl;
                        break;

                    default:
                        // Ignore unrecognized characters
                        break;
                    }
                }
                break;
            }
            }

            // Print CLI prompt for next command
            std::cout << "> " << std::flush;
        }
        else
        {
            // Handle EOF or error condition (e.g., Ctrl+D)
            std::cout << std::endl << "Input stream closed. Exiting..." << std::endl;
            break;
        }
    }

    return nullptr;
}

void ApplicationInit()
{
    // Clear out the device database
    memset(gDevices, 0, sizeof(gDevices));

    // Setup Mock Devices
    Light1.SetReachable(true);
    Light2.SetReachable(true);
    Light1.SetChangeCallback(&HandleDeviceOnOffStatusChanged);
    Light2.SetChangeCallback(&HandleDeviceOnOffStatusChanged);

    TempSensor1.SetReachable(true);
    TempSensor2.SetReachable(true);
    TempSensor1.SetChangeCallback(&HandleDeviceTempSensorStatusChanged);
    TempSensor2.SetChangeCallback(&HandleDeviceTempSensorStatusChanged);

    // Setup devices for action cluster tests
    ActionLight1.SetReachable(true);
    ActionLight2.SetReachable(true);
    ActionLight3.SetReachable(true);
    ActionLight4.SetReachable(true);
    ActionLight1.SetChangeCallback(&HandleDeviceOnOffStatusChanged);
    ActionLight2.SetChangeCallback(&HandleDeviceOnOffStatusChanged);
    ActionLight3.SetChangeCallback(&HandleDeviceOnOffStatusChanged);
    ActionLight4.SetChangeCallback(&HandleDeviceOnOffStatusChanged);

    gComposedDevice.SetReachable(true);
    ComposedTempSensor1.SetReachable(true);
    ComposedTempSensor2.SetReachable(true);
    ComposedPowerSource.SetReachable(true);
    ComposedPowerSource.SetBatChargeLevel(58);
    ComposedTempSensor1.SetChangeCallback(&HandleDeviceTempSensorStatusChanged);
    ComposedTempSensor2.SetChangeCallback(&HandleDeviceTempSensorStatusChanged);
    ComposedPowerSource.SetChangeCallback(&HandleDevicePowerSourceStatusChanged);

    // Set starting endpoint id where dynamic endpoints will be assigned, which
    // will be the next consecutive endpoint id after the last fixed endpoint.
    gFirstDynamicEndpointId = static_cast<chip::EndpointId>(
        static_cast<int>(emberAfEndpointFromIndex(static_cast<uint16_t>(emberAfFixedEndpointCount() - 1))) + 1);
    gCurrentEndpointId = gFirstDynamicEndpointId;

    // Disable last fixed endpoint, which is used as a placeholder for all of the
    // supported clusters so that ZAP will generated the requisite code.
    emberAfEndpointEnableDisable(emberAfEndpointFromIndex(static_cast<uint16_t>(emberAfFixedEndpointCount() - 1)), false);

    // Add light 1 -> will be mapped to ZCL endpoints 3
    AddDeviceEndpoint(&Light1, &bridgedLightEndpoint, Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                      Span<DataVersion>(gLight1DataVersions), 1);

    // Add Temperature Sensor devices --> will be mapped to endpoints 4,5
    AddDeviceEndpoint(&TempSensor1, &bridgedTempSensorEndpoint, Span<const EmberAfDeviceType>(gBridgedTempSensorDeviceTypes),
                      Span<DataVersion>(gTempSensor1DataVersions), 1);
    AddDeviceEndpoint(&TempSensor2, &bridgedTempSensorEndpoint, Span<const EmberAfDeviceType>(gBridgedTempSensorDeviceTypes),
                      Span<DataVersion>(gTempSensor2DataVersions), 1);

    // Add composed Device with two temperature sensors and a power source
    AddDeviceEndpoint(&gComposedDevice, &bridgedComposedDeviceEndpoint, Span<const EmberAfDeviceType>(gBridgedComposedDeviceTypes),
                      Span<DataVersion>(gComposedDeviceDataVersions), 1);
    AddDeviceEndpoint(&ComposedTempSensor1, &bridgedTempSensorEndpoint,
                      Span<const EmberAfDeviceType>(gComposedTempSensorDeviceTypes),
                      Span<DataVersion>(gComposedTempSensor1DataVersions), gComposedDevice.GetEndpointId());
    AddDeviceEndpoint(&ComposedTempSensor2, &bridgedTempSensorEndpoint,
                      Span<const EmberAfDeviceType>(gComposedTempSensorDeviceTypes),
                      Span<DataVersion>(gComposedTempSensor2DataVersions), gComposedDevice.GetEndpointId());

    // Add 4 lights for the Action Clusters tests
    AddDeviceEndpoint(&ActionLight1, &bridgedLightEndpoint, Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                      Span<DataVersion>(gActionLight1DataVersions), 1);
    AddDeviceEndpoint(&ActionLight2, &bridgedLightEndpoint, Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                      Span<DataVersion>(gActionLight2DataVersions), 1);
    AddDeviceEndpoint(&ActionLight3, &bridgedLightEndpoint, Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                      Span<DataVersion>(gActionLight3DataVersions), 1);
    AddDeviceEndpoint(&ActionLight4, &bridgedLightEndpoint, Span<const EmberAfDeviceType>(gBridgedOnOffDeviceTypes),
                      Span<DataVersion>(gActionLight4DataVersions), 1);

    // Because the power source is on the same endpoint as the composed device, it needs to be explicitly added
    gDevices[CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT] = &ComposedPowerSource;
    // This provides power for the composed endpoint
    std::vector<chip::EndpointId> endpointList;
    endpointList.push_back(gComposedDevice.GetEndpointId());
    endpointList.push_back(ComposedTempSensor1.GetEndpointId());
    endpointList.push_back(ComposedTempSensor2.GetEndpointId());
    ComposedPowerSource.SetEndpointList(endpointList);
    ComposedPowerSource.SetEndpointId(gComposedDevice.GetEndpointId());

    gRooms.push_back(&room1);
    gRooms.push_back(&room2);
    gRooms.push_back(&room3);

    gActions.push_back(&action1);
    gActions.push_back(&action2);
    gActions.push_back(&action3);

    {
        pthread_t poll_thread;
        int res = pthread_create(&poll_thread, nullptr, bridge_polling_thread, nullptr);
        if (res)
        {
            printf("Error creating polling thread: %d\n", res);
            exit(1);
        }
    }

    AttributeAccessInterfaceRegistry::Instance().Register(&gPowerAttrAccess);

    // Initialize MQTT Client
    ChipLogProgress(DeviceLayer, "Initializing MQTT Client...");
    mqtt::MQTTClient::Config mqttConfig;
    mqttConfig.broker_host   = "172.23.81.17"; // TODO: Make this configurable
    mqttConfig.broker_port   = 1883;
    mqttConfig.client_id     = "matter_bridge_mqtt";
    mqttConfig.database_path = "matter_devices.db"; // SQLite database path

    gMQTTClient = std::make_unique<mqtt::MQTTClient>(mqttConfig);
    gMQTTClient->SetMessageCallback(OnMQTTMessage);
    gMQTTClient->SetConnectionCallback(OnMQTTConnection);

    // Start MQTT client
    if (gMQTTClient->Connect())
    {
        gMQTTClient->StartAsync();
        ChipLogProgress(DeviceLayer, "MQTT Client started successfully");
    }
    else
    {
        ChipLogError(DeviceLayer, "Failed to start MQTT Client");
    }
}

void ApplicationShutdown()
{
    // Cleanup MQTT Client
    if (gMQTTClient)
    {
        ChipLogProgress(DeviceLayer, "Shutting down MQTT Client...");

        // Display final database statistics
        auto devices = gMQTTClient->GetAllDevices();
        ChipLogProgress(DeviceLayer, "Final database statistics: %zu Matter devices stored", devices.size());

        for (const auto & device : devices)
        {
            ChipLogProgress(DeviceLayer, "Stored Device: ID=%s, Name=%s, State=%s, Homie=%s, Nodes=%s", device.topic_id.c_str(),
                            device.device_name.c_str(), device.state.c_str(), device.homie_version.c_str(), device.nodes.c_str());
        }

        gMQTTClient->Disconnect();
        gMQTTClient->StopAsync();
        gMQTTClient.reset();

        ChipLogProgress(DeviceLayer, "MQTT Client and database connections closed");
    }
}

int main(int argc, char * argv[])
{
    if (ChipLinuxAppInit(argc, argv) != 0)
    {
        return -1;
    }
    ChipLinuxAppMainLoop();
    return 0;
}
