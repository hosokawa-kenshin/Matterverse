/*
 *
 *    Copyright (c) 2020 Project CHIP Authors
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
#include <platform/CHIPDeviceConfig.h>
#include <prototype-server.h>

#if defined(CHIP_IMGUI_ENABLED) && CHIP_IMGUI_ENABLED
#include <imgui_ui/ui.h>
#include <imgui_ui/windows/boolean_state.h>
#include <imgui_ui/windows/occupancy_sensing.h>
#include <imgui_ui/windows/qrcode.h>
#endif

#include <chrono>
#include <iostream>
#include <libgen.h>
#include <sqlite3.h>
#include <thread>
#include <unistd.h>

using namespace chip;
using namespace chip::app;
using namespace chip::app::Clusters;

// -----------------------------------------------------------------------------
std::string dbPath2 = getDBPath();

void estimate_location_from_DB(const std::string & sentinel, int threshold)
{
    sqlite3 * db        = NULL;
    sqlite3_stmt * stmt = NULL;
    int ret             = sqlite3_open_v2(dbPath2.c_str(), &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_FULLMUTEX, NULL);
    if (ret != SQLITE_OK)
    {
        printf("Cannot open database: %s\n", sqlite3_errmsg(db));
        return;
    }

    const char * beacon_sql = "SELECT UUID, Description FROM Beacon;";
    ret                     = sqlite3_prepare_v2(db, beacon_sql, -1, &stmt, NULL);
    if (ret != SQLITE_OK)
    {
        printf("Failed to prepare Beacon statement: %s\n", sqlite3_errmsg(db));
        sqlite3_close(db);
        return;
    }

    printf("\n\n\n\n\n\n");
    while (sqlite3_step(stmt) == SQLITE_ROW)
    {
        const unsigned char * uuid        = sqlite3_column_text(stmt, 0);
        const unsigned char * description = sqlite3_column_text(stmt, 1);

        sqlite3_stmt * room_stmt = NULL;
        const char * room_sql    = "SELECT Mediator.Room FROM Signal "
                                   "JOIN Mediator ON Signal.MediatorUID = Mediator.UID "
                                   "WHERE Signal.BeaconUUID = ? AND Signal.Timestamp >= ? AND Signal.Distance <= ? "
                                   "ORDER BY Signal.Distance ASC LIMIT 1;";

        ret = sqlite3_prepare_v2(db, room_sql, -1, &room_stmt, NULL);
        if (ret != SQLITE_OK)
        {
            printf("Failed to prepare Room statement for UUID: %s\n", sqlite3_errmsg(db));
            sqlite3_close(db);
            return;
        }

        sqlite3_bind_text(room_stmt, 1, reinterpret_cast<const char *>(uuid), -1, SQLITE_STATIC); // Beacon.UUID
        sqlite3_bind_text(room_stmt, 2, sentinel.c_str(), -1, SQLITE_STATIC);                     // Sentinel (Timestamp)
        sqlite3_bind_int(room_stmt, 3, threshold);                                                // RSSI Threshold

        if (sqlite3_step(room_stmt) == SQLITE_ROW)
        {
            const unsigned char * room = sqlite3_column_text(room_stmt, 0);
            printf("%s: %s\n", description, room);
        }
        else
        {
            const unsigned char * room = reinterpret_cast<const unsigned char *>("absence");
            printf("%s: %s\n", description, room);
        }

        sqlite3_finalize(room_stmt);
    }
    printf("\n\n\n\n\n\n");
    sqlite3_finalize(stmt);
    sqlite3_close(db);
}

void startPeriodicEstimation(int threshold)
{
    char * sentinel = getTimestamp();
    while (true)
    {
        estimate_location_from_DB(sentinel, threshold);
        sentinel = getTimestamp();
        std::this_thread::sleep_for(std::chrono::seconds(30));
    }
}

void ApplicationInit() {}

void ApplicationShutdown() {}

int main(int argc, char * argv[])
{
    std::thread estimationThread(startPeriodicEstimation, 10);
    VerifyOrDie(ChipLinuxAppInit(argc, argv) == 0);

#if defined(CHIP_IMGUI_ENABLED) && CHIP_IMGUI_ENABLED
    example::Ui::ImguiUi ui;

    ui.AddWindow(std::make_unique<example::Ui::Windows::QRCode>());
    ui.AddWindow(std::make_unique<example::Ui::Windows::BooleanState>(chip::EndpointId(1), "Contact Sensor"));
    ui.AddWindow(std::make_unique<example::Ui::Windows::OccupancySensing>(chip::EndpointId(1), "Occupancy"));

    ChipLinuxAppMainLoop(&ui);
#else
    ChipLinuxAppMainLoop();
#endif

    return 0;
}
