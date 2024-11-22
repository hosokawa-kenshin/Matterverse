#ifndef SRC_APP_CLUSTERS_PROTOTYPE_CLUSTER_SERVER_SERVER_H_
#define SRC_APP_CLUSTERS_PROTOTYPE_CLUSTER_SERVER_SERVER_H_

#include <app-common/zap-generated/cluster-objects.h>
#include <app/AttributeAccessInterface.h>
#include <app/CommandHandlerInterface.h>
#include <app/ConcreteCommandPath.h>
#include <app/util/af-types.h>
#include <app/util/basic-types.h>
#include <app/util/config.h>
#include <lib/support/Span.h>
#include <platform/CHIPDeviceConfig.h>

#ifdef ZCL_USING_PROTOTYPE_CLUSTER_SERVER
#define PROTOTYPE_NUM_SUPPORTED_ENDPOINTS                                                                                          \
    (MATTER_DM_PROTOTYPE_CLUSTER_SERVER_ENDPOINT_COUNT + CHIP_DEVICE_CONFIG_DYNAMIC_ENDPOINT_COUNT)
#else
#define PROTOTYPE_NUM_SUPPORTED_ENDPOINTS CHIP_DEVICE_CONFIG_ENDPOINT_COUNT_PROTOTYPE
#endif /* ZCL_USING_PROTOTYPE_CLUSTER_SERVER */
static constexpr size_t kNumSupportedEndpoints = PROTOTYPE_NUM_SUPPORTED_ENDPOINTS;

char * getTimestamp();
std::string getDBPath();

namespace chip {
namespace app {
namespace Clusters {
namespace Prototype {

class PrototypeContent
{
public:
    EndpointId endpoint;

    // Attribute List
    uint16_t distance;
    char uidChar[37];
    char MediatorUID[20];
    char log[60];

    PrototypeContent(EndpointId endpoint);
    PrototypeContent();
};

class PrototypeServer : public AttributeAccessInterface, public CommandHandlerInterface
{
public:
    // Register on all endpoints.
    PrototypeServer() :
        AttributeAccessInterface(Optional<EndpointId>::Missing(), Prototype::Id),
        CommandHandlerInterface(Optional<EndpointId>(), Id)
    {}
    static PrototypeServer & Instance();

    // Currently not used, but should be called from a whole-cluster shutdown
    // callback once cluster lifecycle is clearer
    void Shutdown();

    // // Attributes
    CHIP_ERROR Read(const ConcreteReadAttributePath & aPath, AttributeValueEncoder & aEncoder) override;
    CHIP_ERROR Write(const ConcreteDataAttributePath & aPath, AttributeValueDecoder & aDecoder) override;
    void InvokeCommand(HandlerContext & ctx) override;

    // Attribute storage
#if PROTOTYPE_NUM_SUPPORTED_ENDPOINTS > 0
    PrototypeContent content[kNumSupportedEndpoints];
#else
    PrototypeContent * content = nullptr;
#endif

    size_t GetNumSupportedEndpoints() const;
    CHIP_ERROR RegisterEndpoint(EndpointId endpointId);
    CHIP_ERROR UnregisterEndpoint(EndpointId endpointId);

private:
    // both return std::numeric_limits<size_t>::max() for not found
    size_t EndpointIndex(EndpointId endpointId) const;
    size_t NextEmptyIndex() const;
};
} // namespace Prototype
} // namespace Clusters
} // namespace app
} // namespace chip

#endif
