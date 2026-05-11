/**
 * HardwareScanner.c - Phase 34 Stage 1 scanner
 * Collects minimal pre-OS hardware profile without writing to disk.
 */

#include <Uefi.h>

#include <IndustryStandard/MemoryMappedConfigurationSpaceAccessTable.h>
#include <Library/BaseMemoryLib.h>
#include <Library/PrintLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>

#define SECURE_BOOT_VAR_NAME L"SecureBoot"
#define EFI_GLOBAL_VARIABLE_GUID \
  { 0x8BE4DF61, 0x93CA, 0x11D2, {0xAA,0x0D,0x00,0xE0,0x98,0x03,0x2B,0x8C} }

typedef struct {
  UINT32  CpuCount;
  UINT64  RamMb;
  UINT32  DiskCount;
  BOOLEAN DiskSmartErrors;
  CHAR16  GpuVendor[32];
  CHAR16  BootDevice[64];
  CHAR16  UefiVersion[32];
  BOOLEAN SecureBootEnabled;
} KRYOS_HW_PROFILE;

EFI_STATUS
KryosScanHardware(
  OUT KRYOS_HW_PROFILE *Profile
  )
{
  EFI_STATUS                Status;
  EFI_MEMORY_DESCRIPTOR     *MemoryMap;
  EFI_MEMORY_DESCRIPTOR     *Desc;
  UINTN                     MapKey;
  UINTN                     MemoryMapSize;
  UINTN                     DescriptorSize;
  UINT32                    DescriptorVersion;
  UINTN                     Index;
  UINT8                     SecureBootValue;
  UINTN                     SecureBootSize;
  UINT32                    Attr;
  EFI_GUID                  GlobalVarGuid = EFI_GLOBAL_VARIABLE_GUID;

  if (Profile == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  ZeroMem(Profile, sizeof(*Profile));

  Profile->CpuCount = (UINT32)gBS->NumberOfTableEntries;
  Profile->DiskCount = 1;
  Profile->DiskSmartErrors = FALSE;
  StrCpyS(Profile->GpuVendor, sizeof(Profile->GpuVendor) / sizeof(CHAR16), L"UNKNOWN");
  StrCpyS(Profile->BootDevice, sizeof(Profile->BootDevice) / sizeof(CHAR16), L"UEFI_DEFAULT");
  UnicodeSPrint(Profile->UefiVersion, sizeof(Profile->UefiVersion), L"%u", gST->Hdr.Revision);

  MemoryMapSize = 0;
  MemoryMap = NULL;
  Status = gBS->GetMemoryMap(&MemoryMapSize, MemoryMap, &MapKey, &DescriptorSize, &DescriptorVersion);
  if (Status != EFI_BUFFER_TOO_SMALL) {
    return Status;
  }

  Status = gBS->AllocatePool(EfiBootServicesData, MemoryMapSize, (VOID **)&MemoryMap);
  if (EFI_ERROR(Status)) {
    return Status;
  }

  Status = gBS->GetMemoryMap(&MemoryMapSize, MemoryMap, &MapKey, &DescriptorSize, &DescriptorVersion);
  if (!EFI_ERROR(Status)) {
    Profile->RamMb = 0;
    for (Index = 0; Index < MemoryMapSize; Index += DescriptorSize) {
      Desc = (EFI_MEMORY_DESCRIPTOR *)((UINT8 *)MemoryMap + Index);
      Profile->RamMb += EFI_PAGES_TO_SIZE(Desc->NumberOfPages) / (1024 * 1024);
    }
  }

  gBS->FreePool(MemoryMap);

  SecureBootSize = sizeof(SecureBootValue);
  Attr = 0;
  Status = gRT->GetVariable(
                SECURE_BOOT_VAR_NAME,
                &GlobalVarGuid,
                &Attr,
                &SecureBootSize,
                &SecureBootValue
                );

  if (!EFI_ERROR(Status) && SecureBootSize == sizeof(UINT8)) {
    Profile->SecureBootEnabled = (SecureBootValue == 1);
  } else {
    Profile->SecureBootEnabled = FALSE;
  }

  return EFI_SUCCESS;
}
