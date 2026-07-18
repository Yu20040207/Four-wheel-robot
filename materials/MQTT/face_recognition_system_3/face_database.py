import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import cv2
import numpy as np
import face_recognition
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('FaceDatabase')


class FaceDatabase:
    def __init__(self, data_dir: str = 'face_data'):
        self.data_dir = Path(data_dir)
        self.metadata_file = self.data_dir / 'faces_metadata.json'
        self.mapping_file = self.data_dir / 'name_id_mapping.json'
        self.max_images_per_person = 5

        # 创建目录
        self.data_dir.mkdir(exist_ok=True)

        # 初始化数据
        self.metadata = self._load_metadata()
        self.name_to_id_map = self._load_name_id_mapping()
        self.known_face_encodings: List[np.ndarray] = []
        self.known_face_names: List[str] = []

        # 加载已知人脸
        self.load_known_faces()

    def _load_metadata(self) -> Dict[str, Any]:
        """加载人脸元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载元数据失败: {e}")
                return {}
        return {}

    def _load_name_id_mapping(self) -> Dict[str, str]:
        """加载人名到编号的映射"""
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载映射文件失败: {e}")
        return {}

    def _save_name_id_mapping(self) -> bool:
        """保存人名到编号的映射"""
        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(self.name_to_id_map, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存映射文件失败: {e}")
            return False

    def _get_next_available_number(self) -> int:
        """获取下一个可用的编号"""
        existing_numbers = set()

        # 从映射表中提取所有数字编号
        for name, person_id in self.name_to_id_map.items():
            try:
                # 从"User_001"中提取"001"
                if name.startswith("User_"):
                    number_str = name.replace("User_", "")
                    if number_str.isdigit():
                        existing_numbers.add(int(number_str))
                # 从ID中提取数字
                if person_id.isdigit():
                    existing_numbers.add(int(person_id))
            except:
                continue

        # 从元数据中提取所有数字编号
        for person_name in self.metadata.keys():
            try:
                if person_name.startswith("User_"):
                    number_str = person_name.replace("User_", "")
                    if number_str.isdigit():
                        existing_numbers.add(int(number_str))
            except:
                continue

        # 找到下一个可用的编号
        for i in range(1, 1000):
            if i not in existing_numbers:
                return i

        return 999

    def generate_auto_name_and_id(self) -> Tuple[str, str]:
        """生成自动姓名和ID - 姓名和ID的数字部分相同"""
        # 获取下一个可用的编号
        next_number = self._get_next_available_number()

        # 生成姓名和ID，使用相同的数字部分
        auto_name = f"User_{next_number:03d}"
        auto_id = f"{next_number:03d}"

        print(f"🆔 自动生成姓名和ID: {auto_name} [{auto_id}]")
        return auto_name, auto_id

    def assign_id_to_person(self, person_name: str) -> str:
        """为人名分配编号"""
        if person_name in self.name_to_id_map:
            return self.name_to_id_map[person_name]

        # 验证并清理不一致的映射
        self._validate_mapping_consistency()

        # 从姓名中提取数字作为ID
        if person_name.startswith("User_"):
            number_str = person_name.replace("User_", "")
            if number_str.isdigit():
                new_id = number_str
            else:
                new_id = self._get_next_available_number()
        else:
            new_id = self._get_next_available_number()

        new_id_str = f"{int(new_id):03d}"
        self.name_to_id_map[person_name] = new_id_str
        self._save_name_id_mapping()
        logger.info(f"为人名 '{person_name}' 分配编号: {new_id_str}")

        return new_id_str

    def _validate_mapping_consistency(self):
        """验证映射表与目录的一致性"""
        existing_faces = {item.name for item in self.data_dir.iterdir() if item.is_dir()}

        # 找出映射表中存在但目录不存在的人脸
        inconsistent_entries = [
            name for name in self.name_to_id_map
            if name not in existing_faces
        ]

        # 清理不一致的条目
        for name in inconsistent_entries:
            logger.info(f"清理不一致的映射条目: {name}")
            del self.name_to_id_map[name]

        if inconsistent_entries:
            self._save_name_id_mapping()
            logger.info(f"已清理 {len(inconsistent_entries)} 个不一致的映射条目")

    def save_metadata(self) -> bool:
        """保存人脸元数据"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
            return False

    def add_face_image(self, person_name: str, image_data: bytes, person_id: str = None) -> Tuple[bool, str]:
        """添加人脸图像"""
        try:
            # 清理姓名
            clean_name = self._clean_name(person_name)
            if not clean_name:
                return False, "无效的姓名"

            # 验证映射一致性
            self._validate_mapping_consistency()

            # 为人名分配编号
            if person_id is None:
                person_id = self.assign_id_to_person(clean_name)
            else:
                # 使用提供的person_id，但要检查是否可用
                if person_id in self.name_to_id_map.values() and self.name_to_id_map.get(clean_name) != person_id:
                    return False, f"ID {person_id} 已被其他人使用"
                self.name_to_id_map[clean_name] = person_id
                self._save_name_id_mapping()

            person_dir = self.data_dir / clean_name
            person_dir.mkdir(exist_ok=True)

            # 检查图片数量限制
            existing_images = list(person_dir.glob("*.jpg"))
            if len(existing_images) >= self.max_images_per_person:
                return False, f"已达到最大图片数量({self.max_images_per_person})"

            # 生成新文件名并保存
            new_filename = f"{len(existing_images) + 1:02d}.jpg"
            file_path = person_dir / new_filename

            with open(file_path, 'wb') as f:
                f.write(image_data)

            # 处理人脸图像
            if not self._process_face_image(clean_name, image_data):
                file_path.unlink(missing_ok=True)  # 删除图片
                return False, "无法从图片中提取人脸特征，请确保人脸清晰可见"

            # 更新元数据
            self._update_metadata(clean_name, person_id, new_filename)

            logger.info(f"已添加人脸: {clean_name} [{person_id}]")
            return True, f"成功为 {clean_name} [{person_id}] 添加图片"

        except Exception as e:
            logger.error(f"添加人脸失败: {e}")
            return False, f"添加人脸失败: {str(e)}"

    def _clean_name(self, name: str) -> str:
        """清理姓名"""
        return "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()

    def _process_face_image(self, person_name: str, image_data: bytes) -> bool:
        """处理图片并提取人脸编码"""
        try:
            nparr = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is None:
                return False

            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_image)

            if not face_locations:
                return False

            face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
            if not face_encodings:
                return False

            # 添加到已知人脸列表
            self.known_face_names.append(person_name)
            self.known_face_encodings.append(face_encodings[0])

            return True

        except Exception as e:
            logger.error(f"处理人脸图像错误: {e}")
            return False

    def _update_metadata(self, person_name: str, person_id: str, filename: str):
        """更新元数据"""
        if person_name not in self.metadata:
            self.metadata[person_name] = {
                'created_at': datetime.now().isoformat(),
                'image_count': 0,
                'images': [],
                'person_id': person_id
            }
        else:
            # 确保现有的人脸数据也有person_id字段
            if 'person_id' not in self.metadata[person_name]:
                self.metadata[person_name]['person_id'] = person_id

        self.metadata[person_name]['image_count'] += 1
        self.metadata[person_name]['images'].append({
            'filename': filename,
            'added_at': datetime.now().isoformat()
        })

        # 确保映射表也更新
        if person_name not in self.name_to_id_map or self.name_to_id_map[person_name] != person_id:
            self.name_to_id_map[person_name] = person_id
            self._save_name_id_mapping()

        self.save_metadata()

    def search_faces(self, query: str) -> List[Dict[str, Any]]:
        """搜索人脸 - 新增搜索功能"""
        if not query:
            return self.get_all_faces()

        query = query.lower().strip()
        results = []

        for person_name, data in self.metadata.items():
            person_dir = self.data_dir / person_name
            if not person_dir.exists():
                continue

            # 获取正确的ID
            person_id = self.name_to_id_map.get(person_name, data.get('person_id', ''))

            # 搜索条件：姓名包含查询词 或 ID包含查询词
            if (query in person_name.lower() or
                    query in str(person_id).lower()):
                results.append({
                    'name': person_name,
                    'id': person_id,
                    'image_count': data['image_count'],
                    'created_at': data['created_at'],
                    'images': data['images']
                })

        return results


    def get_all_faces(self) -> List[Dict[str, Any]]:
        """获取所有人脸数据"""
        self._validate_mapping_consistency()
        faces = []

        for person_name, data in self.metadata.items():
            person_dir = self.data_dir / person_name
            if person_dir.exists():
                # 优先从映射表中获取ID，如果不存在则从元数据中获取
                person_id = self.name_to_id_map.get(person_name,
                                                    data.get('person_id', '未知'))
                faces.append({
                    'name': person_name,
                    'id': person_id,
                    'image_count': data['image_count'],
                    'created_at': data['created_at'],
                    'images': data['images']
                })
        return faces


    def get_name_id_mapping(self) -> Dict[str, str]:
        """获取人名到编号的映射"""
        return self.name_to_id_map.copy()

    def update_face_id(self, person_name: str, new_id: str) -> Tuple[bool, str]:
        """更新人脸的ID"""
        try:
            # 验证新ID是否已存在
            for name, existing_id in self.name_to_id_map.items():
                if existing_id == new_id and name != person_name:
                    return False, f"ID {new_id} 已经被 {name} 使用"

            # 验证ID格式
            if not new_id.isdigit() or len(new_id) != 3:
                return False, "ID必须是3位数字"

            # 更新ID
            old_id = self.name_to_id_map.get(person_name, "未知")
            self.name_to_id_map[person_name] = new_id
            self._save_name_id_mapping()

            # 更新元数据中的ID
            if person_name in self.metadata:
                self.metadata[person_name]['person_id'] = new_id
                self.save_metadata()

            # 重新加载已知人脸，确保编码与人名关联正确
            self.load_known_faces()

            logger.info(f"已更新ID: {person_name} {old_id} -> {new_id}")
            return True, f"成功将 {person_name} 的ID从 {old_id} 更新为 {new_id}"

        except Exception as e:
            logger.error(f"更新ID失败: {e}")
            return False, f"更新ID失败: {str(e)}"


    def delete_face(self, person_name: str) -> Tuple[bool, str]:
        """删除人脸数据"""
        try:
            if person_name not in self.metadata:
                return False, "未找到该人物"

            # 删除目录
            person_dir = self.data_dir / person_name
            if person_dir.exists():
                import shutil
                shutil.rmtree(person_dir)

                # 删除元数据
                del self.metadata[person_name]
                self.save_metadata()

            # 从已知人脸列表中删除
            indices_to_remove = [
                i for i, name in enumerate(self.known_face_names)
                if name == person_name
            ]
            for index in sorted(indices_to_remove, reverse=True):
                self.known_face_names.pop(index)
                self.known_face_encodings.pop(index)

            logger.info(f"已删除人脸: {person_name}")
            return True, f"成功删除 {person_name} 的人脸数据"

        except Exception as e:
            logger.error(f"删除失败: {e}")
            return False, f"删除失败: {str(e)}"

    def rename_face(self, old_name: str, new_name: str) -> Tuple[bool, str]:
        """重命名人脸 - 修复版本"""
        try:
            # 首先检查原名称是否存在（使用清理后的名称）
            clean_old_name = self._clean_name(old_name)
            if not clean_old_name:
                return False, "无效的原名称"

            if clean_old_name not in self.metadata:
                logger.error(f"重命名失败: 未找到原名称 '{old_name}' (清理后: '{clean_old_name}')")
                logger.error(f"当前元数据中的名称: {list(self.metadata.keys())}")
                return False, f"未找到原名称: {old_name}"

            clean_new_name = self._clean_name(new_name)
            if not clean_new_name:
                return False, "无效的新名称"

            if clean_new_name in self.metadata and clean_new_name != clean_old_name:
                return False, "新名称已存在"

            # 重命名目录
            old_dir = self.data_dir / clean_old_name
            new_dir = self.data_dir / clean_new_name

            if old_dir.exists():
                old_dir.rename(new_dir)
                logger.info(f"已重命名目录: {clean_old_name} -> {clean_new_name}")

            # 更新元数据和映射表
            self.metadata[clean_new_name] = self.metadata.pop(clean_old_name)

            # 更新映射表 - 保持原有的编号
            if clean_old_name in self.name_to_id_map:
                person_id = self.name_to_id_map[clean_old_name]
                del self.name_to_id_map[clean_old_name]
                self.name_to_id_map[clean_new_name] = person_id
                self._save_name_id_mapping()
                logger.info(f"已更新映射表: {clean_old_name} -> {clean_new_name} (ID: {person_id})")

            self.save_metadata()

            # 更新已知人脸列表
            for i in range(len(self.known_face_names)):
                if self.known_face_names[i] == clean_old_name:
                    self.known_face_names[i] = clean_new_name

            logger.info(f"已重命名: {clean_old_name} -> {clean_new_name}")
            return True, f"成功将 {old_name} 重命名为 {new_name}"

        except Exception as e:
            logger.error(f"重命名失败: {e}")
            return False, f"重命名失败: {str(e)}"

    def load_known_faces(self, force_reload: bool = False):
        """加载已知人脸数据 - 优化版本"""
        import time

        # 如果不强制重新加载且已经加载过，则跳过
        if not force_reload and len(self.known_face_encodings) > 0 and len(self.known_face_names) > 0:
            print(f"🔄 已知人脸已加载，跳过重新加载")
            return

        start_time = time.time()

        print(f"🔍 开始加载已知人脸...")
        self._validate_mapping_consistency()
        self.known_face_encodings = []
        self.known_face_names = []

        total_loaded = 0
        person_count = 0
        processed_files = 0

        for person_name, data in self.metadata.items():
            person_count += 1
            person_dir = self.data_dir / person_name
            if not person_dir.exists():
                print(f"⚠️ 目录不存在: {person_dir}")
                continue

            image_files = list(person_dir.glob("*.jpg"))
            if not image_files:
                print(f"⚠️ 没有找到图片文件: {person_dir}")
                continue

            # 只加载第一张图片的人脸编码（通常足够用于识别）
            first_image = image_files[0]
            processed_files += 1

            try:
                print(f"🔍 加载图片 ({processed_files}/{len(self.metadata)}): {first_image.name}")
                image = face_recognition.load_image_file(str(first_image))

                # 使用更快的检测模型
                face_locations = face_recognition.face_locations(image, model="hog")  # 使用hog而不是cnn

                if not face_locations:
                    print(f"⚠️ 未检测到人脸: {first_image.name}")
                    continue

                face_encodings = face_recognition.face_encodings(image, face_locations)
                if face_encodings:
                    self.known_face_names.append(person_name)
                    self.known_face_encodings.append(face_encodings[0])
                    total_loaded += 1
                    print(f"✅ 已加载人脸: {person_name}")
                else:
                    print(f"⚠️ 无法提取人脸编码: {first_image.name}")

            except Exception as e:
                logger.error(f"加载人脸图片错误 {first_image}: {e}")
                continue

        elapsed_time = time.time() - start_time
        print(f"✅ 已加载 {person_count} 个已知人脸，共 {total_loaded} 张人脸编码, 耗时: {elapsed_time:.2f}秒")

        # 验证加载的人脸数量
        if total_loaded == 0:
            print(f"⚠️ 警告: 没有成功加载任何人脸编码")
        else:
            print(f"📊 统计: {len(self.known_face_names)} 个人名, {len(self.known_face_encodings)} 个编码")

    # 在FaceDatabase类中添加以下方法

    def delete_collection_progress(self, person_name: str) -> Tuple[bool, str]:
        """删除采集进度（取消采集时使用）- 修复版本"""
        try:
            clean_name = self._clean_name(person_name)
            if not clean_name:
                return False, "无效的姓名"

            person_dir = self.data_dir / clean_name
            if not person_dir.exists():
                return True, "目录不存在，无需清理"

            # 检查是否是采集中的临时文件
            image_files = list(person_dir.glob("*.jpg"))
            if not image_files:
                return True, "没有图片文件，无需清理"

            # 只删除jpg文件
            deleted_count = 0
            for image_file in image_files:
                try:
                    image_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"删除文件失败 {image_file}: {e}")

            # 如果目录为空，删除目录
            remaining_files = list(person_dir.glob("*"))
            if not remaining_files:
                try:
                    person_dir.rmdir()
                    logger.info(f"已删除空目录: {person_dir}")
                except Exception as e:
                    logger.error(f"删除目录失败 {person_dir}: {e}")

            # 从元数据中删除（先复制键列表避免迭代时修改错误）
            metadata_keys_to_delete = []
            for key in self.metadata.keys():
                if key == clean_name:
                    metadata_keys_to_delete.append(key)

            for key in metadata_keys_to_delete:
                del self.metadata[key]
                logger.info(f"已从元数据中删除: {clean_name}")

            # 保存元数据
            self.save_metadata()

            # 从映射表中删除
            if clean_name in self.name_to_id_map:
                del self.name_to_id_map[clean_name]
                self._save_name_id_mapping()
                logger.info(f"已从映射表中删除: {clean_name}")

            # 从已知人脸列表中删除该人名的编码
            indices_to_remove = []
            for i, name in enumerate(self.known_face_names):
                if name == clean_name:
                    indices_to_remove.append(i)

            # 从后往前删除，避免索引变化
            for index in sorted(indices_to_remove, reverse=True):
                if index < len(self.known_face_names):
                    self.known_face_names.pop(index)
                if index < len(self.known_face_encodings):
                    self.known_face_encodings.pop(index)

            logger.info(f"已从已知人脸列表中删除: {clean_name}")

            return True, f"已删除 {clean_name} 的 {deleted_count} 张图片"

        except Exception as e:
            logger.error(f"删除采集进度失败: {e}")
            return False, f"删除采集进度失败: {str(e)}"



    def fix_all_metadata_ids(self) -> Tuple[bool, str]:
        """修复所有元数据中的ID，确保与映射表一致"""
        try:
            fixed_count = 0
            for person_name in self.metadata.keys():
                if person_name in self.name_to_id_map:
                    person_id = self.name_to_id_map[person_name]
                    if self.metadata[person_name].get('person_id') != person_id:
                        self.metadata[person_name]['person_id'] = person_id
                        fixed_count += 1

            if fixed_count > 0:
                self.save_metadata()
                self.load_known_faces()  # 重新加载确保一致性

            return True, f"已修复 {fixed_count} 条元数据ID记录"

        except Exception as e:
            logger.error(f"修复元数据ID失败: {e}")
            return False, f"修复元数据ID失败: {str(e)}"


    def get_face_images(self, person_name: str) -> List[str]:
        """获取指定人物的所有图片路径"""
        person_dir = self.data_dir / person_name
        if person_dir.exists():
            return [str(person_dir / f) for f in os.listdir(person_dir) if f.endswith('.jpg')]
        return []
