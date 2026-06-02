cmake_minimum_required(VERSION 3.16)
project(tmk VERSION 1.0 LANGUAGES CXX)
 
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
 
set(TMK_SOURCES
    src/tmk.cpp
    src/difficulty_adaptor.cpp
    src/exercise_sequencer.cpp
    src/json_server.cpp
)
 
add_library(tmk_lib STATIC ${TMK_SOURCES})
target_include_directories(tmk_lib PUBLIC include)
 
add_executable(tmk_service src/main.cpp)
target_link_libraries(tmk_service PRIVATE tmk_lib)
 
if(WIN32)
    target_link_libraries(tmk_service PRIVATE ws2_32)
    target_link_libraries(tmk_lib     PRIVATE ws2_32)
endif()
 
if(MSVC)
    target_compile_options(tmk_lib PRIVATE /W4)
else()
    target_compile_options(tmk_lib PRIVATE -Wall -Wextra -O2)
endif()
