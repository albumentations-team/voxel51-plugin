# Capability Report v0.1.0

This snapshot was generated from the release candidate with:

```bash
uv run python scripts/report_transform_capabilities.py
```

## Summary

- version key: `albumentationsx-2.3.7__albu-spec-0.0.6`
- total transforms: `133`
- normal MVP choices: `109`
- `supported`: `68`
- `supported_with_defaults`: `41`

## Status Counts

- `blocked_media_target`: `7`
- `hidden`: `1`
- `requires_external_data`: `7`
- `supported`: `68`
- `supported_with_defaults`: `41`
- `unsupported_output`: `2`
- `unsupported_target`: `7`

## Supported Transform Names

- AdditiveNoise
- AdvancedBlur
- Affine
- AnnotationArtifacts
- AtmosphericFog
- AutoContrast
- Blur
- CLAHE
- CenterCrop
- ChannelDropout
- ChannelShuffle
- ChannelSwap
- ChromaticAberration
- CoarseDropout
- ColorJitter
- Colorize
- Crop
- CropAndPad
- D4
- Defocus
- Dithering
- Downscale
- ElasticTransform
- Emboss
- Enhance
- Equalize
- Erasing
- FancyPCA
- FilmGrain
- FrequencyMasking
- FromFloat
- GaussNoise
- GaussianBlur
- GlassBlur
- GridDistortion
- GridDropout
- GridElasticDeform
- GridMask
- HEStain
- Halftone
- HorizontalFlip
- HueSaturationValue
- ISONoise
- Illumination
- ImageCompression
- InvertImg
- LensFlare
- LetterBox
- LongestMaxSize
- MedianBlur
- ModeFilter
- Morphological
- MotionBlur
- MultiplicativeNoise
- OpticalDistortion
- Pad
- PadIfNeeded
- Perspective
- PhotoMetricDistort
- PiecewiseAffine
- PixelDropout
- PixelSpread
- PlanckianJitter
- PlasmaBrightnessContrast
- PlasmaShadow
- Posterize
- RGBShift
- RandomBrightnessContrast
- RandomCrop
- RandomCropFromBorders
- RandomFog
- RandomGamma
- RandomGravel
- RandomGridShuffle
- RandomRain
- RandomResizedCrop
- RandomRotate90
- RandomScale
- RandomShadow
- RandomSizedCrop
- RandomSnow
- RandomSunFlare
- RandomToneCurve
- Resize
- RingingOvershoot
- Rotate
- SafeRotate
- SaltAndPepper
- Sharpen
- ShiftScaleRotate
- ShotNoise
- SmallestMaxSize
- Solarize
- Spatter
- SquareSymmetry
- Superpixels
- ThinPlateSpline
- TimeMasking
- TimeReverse
- ToGray
- ToRGB
- ToSepia
- Transpose
- UnsharpMask
- VerticalFlip
- Vignetting
- WaterRefraction
- XYMasking
- ZoomBlur

## Excluded Transform Names

`blocked_media_target`

- CenterCrop3D
- CoarseDropout3D
- CubicSymmetry
- GridShuffle3D
- Pad3D
- PadIfNeeded3D
- RandomCrop3D

`hidden`

- NoOp

`requires_external_data`

- CopyAndPaste
- FDA
- HistogramMatching
- Mosaic
- OverlayElements
- PixelDistributionAdaptation
- TextImage

`unsupported_output`

- Normalize
- ToFloat

`unsupported_target`

- AtLeastOneBBoxRandomCrop
- BBoxSafeRandomCrop
- ConstrainedCoarseDropout
- CropNonEmptyMaskIfExists
- MaskDropout
- RandomCropNearBBox
- RandomSizedBBoxSafeCrop
