#include "prototype-server.h"
#include <app-common/zap-generated/attributes/Accessors.h>
#include <app-common/zap-generated/cluster-objects.h>
#include <app-common/zap-generated/ids/Attributes.h>
#include <app-common/zap-generated/ids/Commands.h>
#include <app/AttributeAccessInterfaceRegistry.h>
#include <app/CommandHandler.h>
#include <app/CommandHandlerInterfaceRegistry.h>
#include <app/ConcreteCommandPath.h>
#include <app/EventLogging.h>
#include <app/reporting/reporting.h>
#include <app/util/attribute-storage.h>
#include <app/util/config.h>
#include <app/util/util.h>
#include <chrono>
#include <iostream>
#include <lib/support/CodeUtils.h>
#include <lib/support/logging/CHIPLogging.h>
#include <libgen.h>
#include <sqlite3.h>
#include <thread>
#include <unistd.h>

using namespace chip;
using namespace chip::app;
using namespace chip::app::Clusters;
using namespace chip::app::Clusters::Prototype;
using namespace chip::app::Clusters::Prototype::Attributes;

// -----------------------------------------------------------------------------
char * getTimestamp()
{
    char * timestamp = (char *) malloc(26 * sizeof(char));
    if (!timestamp)
    {
        return NULL;
    }

    time_t now = time(0);
    struct tm tstruct;
    tstruct = *localtime(&now);

    int hours_offset   = 9;
    int minutes_offset = 0;

    strftime(timestamp, 20, "%Y-%m-%dT%H:%M:%S", &tstruct);
    snprintf(timestamp + 19, 7, "%+03d%02d", hours_offset, minutes_offset);

    return timestamp;
}

std::string getDBPath()
{
    char path[1024];
    ssize_t count = readlink("/proc/self/exe", path, sizeof(path));
    if (count == -1)
    {
        std::cerr << "Failed to get executable path." << std::endl;
        return "";
    }
    path[count] = '\0';

    char * dir = dirname(path);

    std::string dbPath = std::string(dir) + "/db/table.db";
    return dbPath;
}

std::string dbPath = getDBPath();

void insertDatabase(char * mediatoruid, char * beaconuuid, uint16_t distance)
{
    sqlite3 * db           = NULL;
    sqlite3_stmt * stmt    = NULL;
    double distance_double = static_cast<double>(distance) / 100;
    char * timestamp       = getTimestamp();

    int ret = sqlite3_open_v2(dbPath.c_str(), &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, NULL);
    if (ret != SQLITE_OK)
    {
        printf("Cannot open database: %s\n", sqlite3_errmsg(db));
        return;
    }

    const char * sql =
        "CREATE TABLE IF NOT EXISTS Signal (ID INT,MediatorUID TEXT, BeaconUUID TEXT, Distance DOUBLE, Timestamp TEXT);";
    ret = sqlite3_exec(db, sql, NULL, NULL, NULL);
    if (ret != SQLITE_OK)
    {
        const char * errorMsg = sqlite3_errmsg(db);
        printf("Failed to create table: %s\n", errorMsg);
        sqlite3_close(db);
        return;
    }

    const char * insertSQL = "INSERT INTO Signal (ID, BeaconUUID, MediatorUID, Distance, Timestamp) VALUES (?, ?, ?, ?, ?);";
    ret                    = sqlite3_prepare_v2(db, insertSQL, -1, &stmt, NULL);

    if (ret != SQLITE_OK)
    {
        printf("Failed to prepare statement: %s\n", sqlite3_errmsg(db));
        sqlite3_close(db);
        return;
    }

    sqlite3_stmt * countStmt;
    const char * countSQL = "SELECT COUNT(*) FROM Signal;";
    ret                   = sqlite3_prepare_v2(db, countSQL, -1, &countStmt, NULL);
    if (ret != SQLITE_OK)
    {
        printf("Failed to prepare statement: %s\n", sqlite3_errmsg(db));
        sqlite3_close(db);
        return;
    }

    ret = sqlite3_step(countStmt);
    int id;
    if (ret == SQLITE_ROW)
    {
        id = sqlite3_column_int(countStmt, 0) + 1;
    }
    else
    {
        printf("Failed to execute statement: %s\n", sqlite3_errmsg(db));
        sqlite3_close(db);
        return;
    }
    sqlite3_finalize(countStmt);
    sqlite3_bind_int(stmt, 1, id);
    sqlite3_bind_text(stmt, 2, beaconuuid, static_cast<int>(strlen(beaconuuid)), SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, mediatoruid, static_cast<int>(strlen(mediatoruid)), SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 4, distance_double);
    sqlite3_bind_text(stmt, 5, timestamp, static_cast<int>(strlen(timestamp)), SQLITE_TRANSIENT);

    ret = sqlite3_step(stmt);

    if (ret != SQLITE_DONE)
    {
        printf("Failed to execute statement: %s\n", sqlite3_errmsg(db));
    }
    else
    {
        printf("Insert finished successfully");
    }
    sqlite3_finalize(stmt);
    sqlite3_close(db);
    free(timestamp);
}
// -----------------------------------------------------------------------------

void MatterPrototypePluginServerInitCallback()
{
    ReturnOnFailure(CommandHandlerInterfaceRegistry::Instance().RegisterCommandHandler(&PrototypeServer::Instance()));
    VerifyOrReturn(AttributeAccessInterfaceRegistry::Instance().Register(&PrototypeServer::Instance()), CHIP_ERROR_INCORRECT_STATE);
}

void emberAfPrototypeClusterServerInitCallback(chip::EndpointId endpoint)
{
    ChipLogProgress(Zcl, "Creating Prototype cluster, Ep %d", endpoint);
    PrototypeServer::Instance().RegisterEndpoint(endpoint);
}

void MatterPrototypeClusterServerShutdownCallback(chip::EndpointId endpoint)
{
    // There's currently no whole-cluster shutdown callback. That would trigger
    // call to `Shutdown`. Thus ep-based shutdown calls `UnregisterEndpoint`
    ChipLogProgress(Zcl, "Shutting down Sample MEI cluster, Ep %d", endpoint);
    PrototypeServer::Instance().UnregisterEndpoint(endpoint);
}
// -----------------------------------------------------------------------------

// AttributeAccessInterfaceを用いた実装を行うとこの関数は呼ばれない
void MatterPrototypeClusterServerAttributeChangedCallback(const chip::app::ConcreteAttributePath & attributePath) {}

namespace chip {
namespace app {
namespace Clusters {
namespace Prototype {
PrototypeContent::PrototypeContent() : PrototypeContent(kInvalidEndpointId) {}

PrototypeContent::PrototypeContent(EndpointId aEndpoint)
{
    endpoint = aEndpoint;
    // Attribute default values
    distance    = 0;
    uidChar[36] = '\0';
}

void PrototypeServer::InvokeCommand(HandlerContext & ctxt) {}

CHIP_ERROR EncodeStringOnSuccess(CHIP_ERROR status, AttributeValueEncoder & encoder, const char * buf, size_t maxBufSize)
{
    ReturnErrorOnFailure(status);
    return encoder.Encode(chip::CharSpan(buf, strnlen(buf, maxBufSize)));
}

CHIP_ERROR PrototypeServer::Read(const ConcreteReadAttributePath & aPath, AttributeValueEncoder & aEncoder)
{
    CHIP_ERROR err       = CHIP_NO_ERROR;
    auto endpoint        = aPath.mEndpointId;
    auto endpointIndex   = EndpointIndex(endpoint);
    auto sendBeaconUUID  = chip::CharSpan(content[endpointIndex].uidChar, strlen(content[endpointIndex].uidChar));
    auto sendMediatorUID = chip::CharSpan(content[endpointIndex].MediatorUID, strlen(content[endpointIndex].MediatorUID));
    if (endpointIndex == std::numeric_limits<size_t>::max())
    {
        return CHIP_IM_GLOBAL_STATUS(UnsupportedEndpoint);
    }

    switch (aPath.mAttributeId)
    {
    case Attributes::Distance::Id:
        err = aEncoder.Encode(content[endpointIndex].distance);
        break;

    case Attributes::BeaconUUID::Id: {
        err = aEncoder.Encode(sendBeaconUUID);
        break;
    }

    case Attributes::MediatorUID::Id: {
        err = aEncoder.Encode(sendMediatorUID);
        break;
    }

    default:
        break;
    }

    return err;
}

CHIP_ERROR PrototypeServer::Write(const ConcreteDataAttributePath & aPath, AttributeValueDecoder & aDecoder)
{
    CHIP_ERROR err     = CHIP_NO_ERROR;
    auto endpoint      = aPath.mEndpointId;
    auto endpointIndex = EndpointIndex(endpoint);
    chip::CharSpan recvdata;
    std::string uidtmp;
    if (endpointIndex == std::numeric_limits<size_t>::max())
    {
        return CHIP_IM_GLOBAL_STATUS(UnsupportedEndpoint);
    }

    switch (aPath.mAttributeId)
    {
    case Attributes::Distance::Id: {
        ReturnErrorOnFailure(aDecoder.Decode(content[endpointIndex].distance));
        break;
    }
    case Attributes::BeaconUUID::Id: {
        ReturnErrorOnFailure(aDecoder.Decode(recvdata));
        if (recvdata.data() != nullptr && recvdata.size() > 0)
        {
            memcpy(content[endpointIndex].uidChar, recvdata.data(), recvdata.size());
        }
        break;
    }
    case Attributes::MediatorUID::Id: {
        ReturnErrorOnFailure(aDecoder.Decode(recvdata));
        if (recvdata.data() != nullptr && recvdata.size() > 0)
        {
            memcpy(content[endpointIndex].MediatorUID, recvdata.data(), recvdata.size());
        }
        break;
    }

    case Attributes::LogEntry::Id: {
        ReturnErrorOnFailure(aDecoder.Decode(recvdata));
        if (recvdata.data() != nullptr && recvdata.size() > 0)
        {
            memcpy(content[endpointIndex].log, recvdata.data(), recvdata.size());

            std::string logStr(content[endpointIndex].log);
            size_t colonPos1 = logStr.find(':');
            if (colonPos1 != std::string::npos)
            {
                size_t colonPos2 = logStr.find(':', colonPos1 + 1);
                if (colonPos2 != std::string::npos)
                {
                    std::string uuid        = logStr.substr(0, colonPos1);
                    std::string distanceStr = logStr.substr(colonPos1 + 1, colonPos2 - colonPos1 - 1);

                    uint16_t distance       = static_cast<uint16_t>(std::stoul(distanceStr));
                    std::string mediatoruid = logStr.substr(colonPos2 + 1, 17);

                    memcpy(content[endpointIndex].uidChar, uuid.c_str(), uuid.size() + 1);
                    content[endpointIndex].distance = distance;
                    memcpy(content[endpointIndex].MediatorUID, mediatoruid.c_str(), mediatoruid.size() + 1);
                }
            }

            insertDatabase(content[endpointIndex].MediatorUID, content[endpointIndex].uidChar, content[endpointIndex].distance);
        }

        break;
    }
    default:
        break;
    }

    return err;
}

PrototypeServer & PrototypeServer::Instance()
{
    static PrototypeServer PrototypeServer;
    return PrototypeServer;
}

void PrototypeServer::Shutdown()
{
    for (size_t i = 0; i < kNumSupportedEndpoints; ++i)
    {
        content[i].endpoint = kInvalidEndpointId;
    }
}

size_t PrototypeServer::GetNumSupportedEndpoints() const
{
    return kNumSupportedEndpoints;
}

CHIP_ERROR PrototypeServer::RegisterEndpoint(EndpointId endpointId)
{
    size_t endpointIndex = NextEmptyIndex();
    if (endpointIndex == std::numeric_limits<size_t>::max())
    {
        return CHIP_ERROR_NO_MEMORY;
    }
    content[endpointIndex] = PrototypeContent(endpointId);
    return CHIP_NO_ERROR;
}

CHIP_ERROR PrototypeServer::UnregisterEndpoint(EndpointId endpointId)
{
    size_t endpointIndex = EndpointIndex(endpointId);
    if (endpointIndex == std::numeric_limits<size_t>::max())
    {
        return CHIP_ERROR_INVALID_ARGUMENT;
    }

    content[endpointIndex].endpoint = kInvalidEndpointId;
    return CHIP_NO_ERROR;
}

size_t PrototypeServer::EndpointIndex(EndpointId endpointId) const
{
    for (size_t i = 0; i < kNumSupportedEndpoints; ++i)
    {
        if (content[i].endpoint == endpointId)
        {
            return i;
        }
    }
    return std::numeric_limits<size_t>::max();
}

size_t PrototypeServer::NextEmptyIndex() const
{
    for (size_t i = 0; i < kNumSupportedEndpoints; ++i)
    {
        if (content[i].endpoint == kInvalidEndpointId)
        {
            return i;
        }
    }
    return std::numeric_limits<size_t>::max();
}

} // namespace Prototype
} // namespace Clusters
} // namespace app
} // namespace chip
