/*
 *
 *    Copyright (c) 2022 Project CHIP Authors
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

#include "BindingHandler.h"
#include "app/CommandSender.h"
#include "app/clusters/bindings/BindingManager.h"
#include "app/server/Server.h"
#include "controller/InvokeInteraction.h"
#include "platform/CHIPDeviceLayer.h"
#include <app/CommandPathParams.h>
#include <app/InteractionModelEngine.h>
#include <app/clusters/bindings/bindings.h>
#include <app/data-model/Encode.h>
#include <lib/core/TLV.h>
#include <lib/support/CodeUtils.h>
#include <string.h>

#if CONFIG_ENABLE_CHIP_SHELL
#include "lib/shell/Engine.h"
#include "lib/shell/commands/Help.h"
#endif // ENABLE_CHIP_SHELL

using namespace chip;
using namespace chip::app;

#if CONFIG_ENABLE_CHIP_SHELL
using Shell::Engine;
using Shell::shell_command_t;
using Shell::streamer_get;
using Shell::streamer_printf;

Engine sShellSwitchSubCommands;
Engine sShellSwitchOnOffSubCommands;
Engine sShellSwitchLocationDetectorSubCommands;

Engine sShellSwitchGroupsSubCommands;
Engine sShellSwitchGroupsOnOffSubCommands;

Engine sShellSwitchBindingSubCommands;
#endif // defined(ENABLE_CHIP_SHELL)

namespace {

// Location Detector Cluster ID
constexpr chip::ClusterId kLocationDetectorClusterId = 0xFFF1FC01;
constexpr chip::CommandId kRecordEntryCommandId      = 0x00;

void ProcessLocationDetectorUnicastBindingCommand(const char * entryData, const EmberBindingTableEntry & binding,
                                                  Messaging::ExchangeManager * exchangeMgr, const SessionHandle & sessionHandle)
{
    ChipLogProgress(NotSpecified, "Sending LocationDetector RecordEntry command with entry: %s", entryData);

    // Create command sender
    app::CommandSender * commandSender = chip::Platform::New<app::CommandSender>(nullptr, exchangeMgr);
    VerifyOrReturn(commandSender != nullptr, ChipLogError(NotSpecified, "Failed to allocate CommandSender"));

    // Prepare command path with proper constructor
    app::CommandPathParams cmdParams(binding.remote, 0, kLocationDetectorClusterId, kRecordEntryCommandId,
                                     (app::CommandPathFlags::kEndpointIdValid));

    // Start command with new API
    app::CommandSender::PrepareCommandParameters prepareCommandParams;
    prepareCommandParams.SetStartDataStruct(true);

    CHIP_ERROR err = commandSender->PrepareCommand(cmdParams, prepareCommandParams);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to prepare command: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    // Encode command data
    TLV::TLVWriter * writer = commandSender->GetCommandDataIBTLVWriter();
    if (writer == nullptr)
    {
        ChipLogError(NotSpecified, "Failed to get TLV writer");
        chip::Platform::Delete(commandSender);
        return;
    }

    err = writer->PutString(TLV::ContextTag(0), entryData);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to encode entry data: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    app::CommandSender::FinishCommandParameters finishCommandParams;
    finishCommandParams.SetEndDataStruct(true);

    err = commandSender->FinishCommand(finishCommandParams);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to finish command: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    // Send command
    err = commandSender->SendCommandRequest(sessionHandle);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to send command: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    ChipLogProgress(NotSpecified, "LocationDetector RecordEntry command sent successfully");
}

void ProcessOnOffUnicastBindingCommand(CommandId commandId, const EmberBindingTableEntry & binding,
                                       Messaging::ExchangeManager * exchangeMgr, const SessionHandle & sessionHandle)
{
    auto onSuccess = [](const ConcreteCommandPath & commandPath, const StatusIB & status, const auto & dataResponse) {
        ChipLogProgress(NotSpecified, "OnOff command succeeds");
    };

    auto onFailure = [](CHIP_ERROR error) {
        ChipLogError(NotSpecified, "OnOff command failed: %" CHIP_ERROR_FORMAT, error.Format());
    };

    switch (commandId)
    {
    case Clusters::OnOff::Commands::Toggle::Id:
        Clusters::OnOff::Commands::Toggle::Type toggleCommand;
        Controller::InvokeCommandRequest(exchangeMgr, sessionHandle, binding.remote, toggleCommand, onSuccess, onFailure);
        break;

    case Clusters::OnOff::Commands::On::Id:
        Clusters::OnOff::Commands::On::Type onCommand;
        Controller::InvokeCommandRequest(exchangeMgr, sessionHandle, binding.remote, onCommand, onSuccess, onFailure);
        break;

    case Clusters::OnOff::Commands::Off::Id:
        Clusters::OnOff::Commands::Off::Type offCommand;
        Controller::InvokeCommandRequest(exchangeMgr, sessionHandle, binding.remote, offCommand, onSuccess, onFailure);
        break;
    }
}

void ProcessOnOffGroupBindingCommand(CommandId commandId, const EmberBindingTableEntry & binding)
{
    Messaging::ExchangeManager & exchangeMgr = Server::GetInstance().GetExchangeManager();

    switch (commandId)
    {
    case Clusters::OnOff::Commands::Toggle::Id:
        Clusters::OnOff::Commands::Toggle::Type toggleCommand;
        Controller::InvokeGroupCommandRequest(&exchangeMgr, binding.fabricIndex, binding.groupId, toggleCommand);
        break;

    case Clusters::OnOff::Commands::On::Id:
        Clusters::OnOff::Commands::On::Type onCommand;
        Controller::InvokeGroupCommandRequest(&exchangeMgr, binding.fabricIndex, binding.groupId, onCommand);

        break;

    case Clusters::OnOff::Commands::Off::Id:
        Clusters::OnOff::Commands::Off::Type offCommand;
        Controller::InvokeGroupCommandRequest(&exchangeMgr, binding.fabricIndex, binding.groupId, offCommand);
        break;
    }
}

void LightSwitchChangedHandler(const EmberBindingTableEntry & binding, OperationalDeviceProxy * peer_device, void * context)
{
    VerifyOrReturn(context != nullptr, ChipLogError(NotSpecified, "OnDeviceConnectedFn: context is null"));
    BindingCommandData * data = static_cast<BindingCommandData *>(context);

    if (binding.type == MATTER_MULTICAST_BINDING && data->isGroup)
    {
        switch (data->clusterId)
        {
        case Clusters::OnOff::Id:
            ProcessOnOffGroupBindingCommand(data->commandId, binding);
            break;
        }
    }
    else if (binding.type == MATTER_UNICAST_BINDING && !data->isGroup)
    {
        switch (data->clusterId)
        {
        case Clusters::OnOff::Id:
            VerifyOrDie(peer_device != nullptr && peer_device->ConnectionReady());
            ProcessOnOffUnicastBindingCommand(data->commandId, binding, peer_device->GetExchangeManager(),
                                              peer_device->GetSecureSession().Value());
            break;
        case kLocationDetectorClusterId:
            VerifyOrDie(peer_device != nullptr && peer_device->ConnectionReady());
            if (data->entryData != nullptr)
            {
                ProcessLocationDetectorUnicastBindingCommand(data->entryData, binding, peer_device->GetExchangeManager(),
                                                             peer_device->GetSecureSession().Value());
            }
            break;
        }
    }
}

void LightSwitchContextReleaseHandler(void * context)
{
    VerifyOrReturn(context != nullptr, ChipLogError(NotSpecified, "Invalid context for Light switch context release handler"));

    BindingCommandData * data = static_cast<BindingCommandData *>(context);

    // Free entry data if allocated
    if (data->entryData != nullptr)
    {
        chip::Platform::MemoryFree(const_cast<char *>(data->entryData));
    }

    Platform::Delete(data);
}

void InitBindingHandlerInternal(intptr_t arg)
{
    auto & server = chip::Server::GetInstance();
    chip::BindingManager::GetInstance().Init(
        { &server.GetFabricTable(), server.GetCASESessionManager(), &server.GetPersistentStorage() });
    chip::BindingManager::GetInstance().RegisterBoundDeviceChangedHandler(LightSwitchChangedHandler);
    chip::BindingManager::GetInstance().RegisterBoundDeviceContextReleaseHandler(LightSwitchContextReleaseHandler);
}

// Callback for device connection (direct command)
void OnDeviceConnectedForDirectCommand(void * context, Messaging::ExchangeManager & exchangeMgr,
                                       const SessionHandle & sessionHandle)
{
    DirectCommandData * data = static_cast<DirectCommandData *>(context);

    ChipLogProgress(NotSpecified, "Device connected, sending command with entry: %s", data->entryData);

    // Create command sender
    CommandSender * commandSender = chip::Platform::New<CommandSender>(nullptr, &exchangeMgr);
    VerifyOrReturn(commandSender != nullptr, ChipLogError(NotSpecified, "Failed to allocate CommandSender"));

    // Prepare command path
    CommandPathParams cmdParams(data->endpoint, 0, kLocationDetectorClusterId, kRecordEntryCommandId,
                                (CommandPathFlags::kEndpointIdValid));

    CommandSender::PrepareCommandParameters prepareCommandParams;
    prepareCommandParams.SetStartDataStruct(true);

    CHIP_ERROR err = commandSender->PrepareCommand(cmdParams, prepareCommandParams);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to prepare command: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    // Encode command data
    TLV::TLVWriter * writer = commandSender->GetCommandDataIBTLVWriter();
    if (writer == nullptr)
    {
        ChipLogError(NotSpecified, "Failed to get TLV writer");
        chip::Platform::Delete(commandSender);
        return;
    }

    err = writer->PutString(TLV::ContextTag(0), data->entryData);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to encode entry data: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    CommandSender::FinishCommandParameters finishCommandParams;
    finishCommandParams.SetEndDataStruct(true);

    err = commandSender->FinishCommand(finishCommandParams);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to finish command: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    // Send command
    err = commandSender->SendCommandRequest(sessionHandle);
    if (err != CHIP_NO_ERROR)
    {
        ChipLogError(NotSpecified, "Failed to send command: %" CHIP_ERROR_FORMAT, err.Format());
        chip::Platform::Delete(commandSender);
        return;
    }

    ChipLogProgress(NotSpecified, "LocationDetector command sent successfully");

    // Cleanup
    if (data->entryData != nullptr)
    {
        chip::Platform::MemoryFree(data->entryData);
    }
    chip::Platform::Delete(data);
}

void OnDeviceConnectionFailureForDirectCommand(void * context, const ScopedNodeId & peerId, CHIP_ERROR error)
{
    DirectCommandData * data = static_cast<DirectCommandData *>(context);
    ChipLogError(NotSpecified, "Failed to connect to node 0x" ChipLogFormatX64 ": %" CHIP_ERROR_FORMAT,
                 ChipLogValueX64(peerId.GetNodeId()), error.Format());

    // Cleanup
    if (data->entryData != nullptr)
    {
        chip::Platform::MemoryFree(data->entryData);
    }
    chip::Platform::Delete(data);
}

// Direct command sending (without binding)
void SendLocationDetectorCommandInternal(intptr_t context)
{
    VerifyOrReturn(context != 0, ChipLogError(NotSpecified, "SendLocationDetectorCommandInternal - Invalid context"));

    DirectCommandData * data = reinterpret_cast<DirectCommandData *>(context);

    ChipLogProgress(NotSpecified, "Sending LocationDetector command directly to node 0x" ChipLogFormatX64 " endpoint %u",
                    ChipLogValueX64(data->nodeId), data->endpoint);

    auto * onConnected = chip::Platform::New<Callback::Callback<OnDeviceConnected>>(OnDeviceConnectedForDirectCommand, data);
    auto * onFailure =
        chip::Platform::New<Callback::Callback<OnDeviceConnectionFailure>>(OnDeviceConnectionFailureForDirectCommand, data);

    auto & server = Server::GetInstance();
    server.GetCASESessionManager()->FindOrEstablishSession(ScopedNodeId(data->nodeId, 1), onConnected, onFailure);
}

void SendLocationDetectorCommand(NodeId nodeId, EndpointId endpoint, const char * entryData)
{
    DirectCommandData * data = chip::Platform::New<DirectCommandData>();
    data->nodeId             = nodeId;
    data->endpoint           = endpoint;

    // Allocate and copy entry data
    size_t entryLen = strlen(entryData) + 1;
    data->entryData = static_cast<char *>(chip::Platform::MemoryAlloc(entryLen));
    if (data->entryData != nullptr)
    {
        memcpy(data->entryData, entryData, entryLen);
    }

    DeviceLayer::PlatformMgr().ScheduleWork(SendLocationDetectorCommandInternal, reinterpret_cast<intptr_t>(data));
}

#ifdef CONFIG_ENABLE_CHIP_SHELL

/********************************************************
 * Switch shell functions
 *********************************************************/

CHIP_ERROR SwitchHelpHandler(int argc, char ** argv)
{
    sShellSwitchSubCommands.ForEachCommand(Shell::PrintCommandHelp, nullptr);
    return CHIP_NO_ERROR;
}

CHIP_ERROR SwitchCommandHandler(int argc, char ** argv)
{
    if (argc == 0)
    {
        return SwitchHelpHandler(argc, argv);
    }

    return sShellSwitchSubCommands.ExecCommand(argc, argv);
}

/********************************************************
 * OnOff switch shell functions
 *********************************************************/

CHIP_ERROR OnOffHelpHandler(int argc, char ** argv)
{
    sShellSwitchOnOffSubCommands.ForEachCommand(Shell::PrintCommandHelp, nullptr);
    return CHIP_NO_ERROR;
}

CHIP_ERROR OnOffSwitchCommandHandler(int argc, char ** argv)
{
    if (argc == 0)
    {
        return OnOffHelpHandler(argc, argv);
    }

    return sShellSwitchOnOffSubCommands.ExecCommand(argc, argv);
}

CHIP_ERROR OnSwitchCommandHandler(int argc, char ** argv)
{
    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = Clusters::OnOff::Commands::On::Id;
    data->clusterId           = Clusters::OnOff::Id;

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

CHIP_ERROR OffSwitchCommandHandler(int argc, char ** argv)
{
    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = Clusters::OnOff::Commands::Off::Id;
    data->clusterId           = Clusters::OnOff::Id;

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

CHIP_ERROR ToggleSwitchCommandHandler(int argc, char ** argv)
{
    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = Clusters::OnOff::Commands::Toggle::Id;
    data->clusterId           = Clusters::OnOff::Id;

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

/********************************************************
 * Location Detector switch shell functions
 *********************************************************/

CHIP_ERROR LocationDetectorHelpHandler(int argc, char ** argv)
{
    sShellSwitchLocationDetectorSubCommands.ForEachCommand(Shell::PrintCommandHelp, nullptr);
    return CHIP_NO_ERROR;
}

CHIP_ERROR LocationDetectorSwitchCommandHandler(int argc, char ** argv)
{
    if (argc == 0)
    {
        return LocationDetectorHelpHandler(argc, argv);
    }

    return sShellSwitchLocationDetectorSubCommands.ExecCommand(argc, argv);
}

CHIP_ERROR RecordEntrySwitchCommandHandler(int argc, char ** argv)
{
    VerifyOrReturnError(argc == 1, CHIP_ERROR_INVALID_ARGUMENT);

    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = 0x00; // RecordEntry command ID
    data->clusterId           = kLocationDetectorClusterId;

    // Allocate memory for entry data
    size_t entryLen  = strlen(argv[0]) + 1;
    char * entryCopy = static_cast<char *>(chip::Platform::MemoryAlloc(entryLen));
    if (entryCopy != nullptr)
    {
        memcpy(entryCopy, argv[0], entryLen);
        data->entryData = entryCopy;
    }

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

CHIP_ERROR DirectRecordEntrySwitchCommandHandler(int argc, char ** argv)
{
    VerifyOrReturnError(argc == 3, CHIP_ERROR_INVALID_ARGUMENT);

    chip::NodeId nodeId       = static_cast<chip::NodeId>(strtoul(argv[0], nullptr, 0));
    chip::EndpointId endpoint = static_cast<chip::EndpointId>(strtoul(argv[1], nullptr, 0));
    const char * entryData    = argv[2];

    ChipLogProgress(NotSpecified, "Sending direct command to node 0x" ChipLogFormatX64 " endpoint %u", ChipLogValueX64(nodeId),
                    endpoint);

    SendLocationDetectorCommand(nodeId, endpoint, entryData);
    return CHIP_NO_ERROR;
}

/********************************************************
 * bind switch shell functions
 *********************************************************/

CHIP_ERROR BindingHelpHandler(int argc, char ** argv)
{
    sShellSwitchBindingSubCommands.ForEachCommand(Shell::PrintCommandHelp, nullptr);
    return CHIP_NO_ERROR;
}

CHIP_ERROR BindingSwitchCommandHandler(int argc, char ** argv)
{
    if (argc == 0)
    {
        return BindingHelpHandler(argc, argv);
    }

    return sShellSwitchBindingSubCommands.ExecCommand(argc, argv);
}

CHIP_ERROR BindingGroupBindCommandHandler(int argc, char ** argv)
{
    VerifyOrReturnError(argc == 2, CHIP_ERROR_INVALID_ARGUMENT);

    EmberBindingTableEntry * entry = Platform::New<EmberBindingTableEntry>();
    entry->type                    = MATTER_MULTICAST_BINDING;
    entry->fabricIndex             = atoi(argv[0]);
    entry->groupId                 = atoi(argv[1]);
    entry->local                   = 1; // Hardcoded to endpoint 1 for now
    entry->clusterId.emplace(6);        // Hardcoded to OnOff cluster for now

    DeviceLayer::PlatformMgr().ScheduleWork(BindingWorkerFunction, reinterpret_cast<intptr_t>(entry));
    return CHIP_NO_ERROR;
}

CHIP_ERROR BindingUnicastBindCommandHandler(int argc, char ** argv)
{
    VerifyOrReturnError(argc == 3, CHIP_ERROR_INVALID_ARGUMENT);

    EmberBindingTableEntry * entry = Platform::New<EmberBindingTableEntry>();
    entry->type                    = MATTER_UNICAST_BINDING;
    entry->fabricIndex             = atoi(argv[0]);
    entry->nodeId                  = atoi(argv[1]);
    entry->local                   = 1; // Hardcoded to endpoint 1 for now
    entry->remote                  = atoi(argv[2]);
    entry->clusterId.emplace(kLocationDetectorClusterId); // Location Detector cluster

    DeviceLayer::PlatformMgr().ScheduleWork(BindingWorkerFunction, reinterpret_cast<intptr_t>(entry));
    return CHIP_NO_ERROR;
}

/********************************************************
 * Groups switch shell functions
 *********************************************************/

CHIP_ERROR GroupsHelpHandler(int argc, char ** argv)
{
    sShellSwitchGroupsSubCommands.ForEachCommand(Shell::PrintCommandHelp, nullptr);
    return CHIP_NO_ERROR;
}

CHIP_ERROR GroupsSwitchCommandHandler(int argc, char ** argv)
{
    if (argc == 0)
    {
        return GroupsHelpHandler(argc, argv);
    }

    return sShellSwitchGroupsSubCommands.ExecCommand(argc, argv);
}

/********************************************************
 * Groups OnOff switch shell functions
 *********************************************************/

CHIP_ERROR GroupsOnOffHelpHandler(int argc, char ** argv)
{
    sShellSwitchGroupsOnOffSubCommands.ForEachCommand(Shell::PrintCommandHelp, nullptr);
    return CHIP_NO_ERROR;
}

CHIP_ERROR GroupsOnOffSwitchCommandHandler(int argc, char ** argv)
{
    if (argc == 0)
    {
        return GroupsOnOffHelpHandler(argc, argv);
    }

    return sShellSwitchGroupsOnOffSubCommands.ExecCommand(argc, argv);
}

CHIP_ERROR GroupOnSwitchCommandHandler(int argc, char ** argv)
{
    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = Clusters::OnOff::Commands::On::Id;
    data->clusterId           = Clusters::OnOff::Id;
    data->isGroup             = true;

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

CHIP_ERROR GroupOffSwitchCommandHandler(int argc, char ** argv)
{
    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = Clusters::OnOff::Commands::Off::Id;
    data->clusterId           = Clusters::OnOff::Id;
    data->isGroup             = true;

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

CHIP_ERROR GroupToggleSwitchCommandHandler(int argc, char ** argv)
{
    BindingCommandData * data = Platform::New<BindingCommandData>();
    data->commandId           = Clusters::OnOff::Commands::Toggle::Id;
    data->clusterId           = Clusters::OnOff::Id;
    data->isGroup             = true;

    DeviceLayer::PlatformMgr().ScheduleWork(SwitchWorkerFunction, reinterpret_cast<intptr_t>(data));
    return CHIP_NO_ERROR;
}

/**
 * @brief configures switch matter shell
 *
 */
static void RegisterSwitchCommands()
{

    static const shell_command_t sSwitchSubCommands[] = {
        { &SwitchHelpHandler, "help", "Usage: switch <subcommand>" },
        { &OnOffSwitchCommandHandler, "onoff", " Usage: switch onoff <subcommand>" },
        { &LocationDetectorSwitchCommandHandler, "location", "Usage: switch location <subcommand>" },
        { &GroupsSwitchCommandHandler, "groups", "Usage: switch groups <subcommand>" },
        { &BindingSwitchCommandHandler, "binding", "Usage: switch binding <subcommand>" }
    };

    static const shell_command_t sSwitchOnOffSubCommands[] = {
        { &OnOffHelpHandler, "help", "Usage : switch ononff <subcommand>" },
        { &OnSwitchCommandHandler, "on", "Sends on command to bound lighting app" },
        { &OffSwitchCommandHandler, "off", "Sends off command to bound lighting app" },
        { &ToggleSwitchCommandHandler, "toggle", "Sends toggle command to bound lighting app" }
    };

    static const shell_command_t sSwitchLocationDetectorSubCommands[] = {
        { &LocationDetectorHelpHandler, "help", "Usage: switch location <subcommand>" },
        { &RecordEntrySwitchCommandHandler, "record", "Usage: switch location record <entry_data>" },
        { &DirectRecordEntrySwitchCommandHandler, "direct", "Usage: switch location direct <node_id> <endpoint> <entry_data>" }
    };

    static const shell_command_t sSwitchGroupsSubCommands[] = { { &GroupsHelpHandler, "help", "Usage: switch groups <subcommand>" },
                                                                { &GroupsOnOffSwitchCommandHandler, "onoff",
                                                                  "Usage: switch groups onoff <subcommand>" } };

    static const shell_command_t sSwitchGroupsOnOffSubCommands[] = {
        { &GroupsOnOffHelpHandler, "help", "Usage: switch groups onoff <subcommand>" },
        { &GroupOnSwitchCommandHandler, "on", "Sends on command to bound group" },
        { &GroupOffSwitchCommandHandler, "off", "Sends off command to bound group" },
        { &GroupToggleSwitchCommandHandler, "toggle", "Sends toggle command to group" }
    };

    static const shell_command_t sSwitchBindingSubCommands[] = {
        { &BindingHelpHandler, "help", "Usage: switch binding <subcommand>" },
        { &BindingGroupBindCommandHandler, "group", "Usage: switch binding group <fabric index> <group id>" },
        { &BindingUnicastBindCommandHandler, "unicast", "Usage: switch binding unicast <fabric index> <node id> <endpoint>" }
    };

    static const shell_command_t sSwitchCommand = { &SwitchCommandHandler, "switch",
                                                    "Light-switch commands. Usage: switch <subcommand>" };

    sShellSwitchGroupsOnOffSubCommands.RegisterCommands(sSwitchGroupsOnOffSubCommands, ArraySize(sSwitchGroupsOnOffSubCommands));
    sShellSwitchOnOffSubCommands.RegisterCommands(sSwitchOnOffSubCommands, ArraySize(sSwitchOnOffSubCommands));
    sShellSwitchLocationDetectorSubCommands.RegisterCommands(sSwitchLocationDetectorSubCommands,
                                                             ArraySize(sSwitchLocationDetectorSubCommands));
    sShellSwitchGroupsSubCommands.RegisterCommands(sSwitchGroupsSubCommands, ArraySize(sSwitchGroupsSubCommands));
    sShellSwitchBindingSubCommands.RegisterCommands(sSwitchBindingSubCommands, ArraySize(sSwitchBindingSubCommands));
    sShellSwitchSubCommands.RegisterCommands(sSwitchSubCommands, ArraySize(sSwitchSubCommands));

    Engine::Root().RegisterCommands(&sSwitchCommand, 1);
}
#endif // ENABLE_CHIP_SHELL

} // namespace

/********************************************************
 * Switch functions
 *********************************************************/

void SwitchWorkerFunction(intptr_t context)
{
    VerifyOrReturn(context != 0, ChipLogError(NotSpecified, "SwitchWorkerFunction - Invalid work data"));

    BindingCommandData * data = reinterpret_cast<BindingCommandData *>(context);
    BindingManager::GetInstance().NotifyBoundClusterChanged(data->localEndpointId, data->clusterId, static_cast<void *>(data));
}

void BindingWorkerFunction(intptr_t context)
{
    VerifyOrReturn(context != 0, ChipLogError(NotSpecified, "BindingWorkerFunction - Invalid work data"));

    EmberBindingTableEntry * entry = reinterpret_cast<EmberBindingTableEntry *>(context);
    AddBindingEntry(*entry);

    Platform::Delete(entry);
}

CHIP_ERROR InitBindingHandler()
{
    // The initialization of binding manager will try establishing connection with unicast peers
    // so it requires the Server instance to be correctly initialized. Post the init function to
    // the event queue so that everything is ready when initialization is conducted.
    chip::DeviceLayer::PlatformMgr().ScheduleWork(InitBindingHandlerInternal);
#if CONFIG_ENABLE_CHIP_SHELL
    RegisterSwitchCommands();
#endif
    return CHIP_NO_ERROR;
}
