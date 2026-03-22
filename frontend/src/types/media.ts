export type OutputFormat = 'jpg' | 'png' | 'webp' | 'tiff';

export interface ConvertImageParams {
    readonly file: File;
    readonly output_format: OutputFormat;
    readonly quality?: number;
}
